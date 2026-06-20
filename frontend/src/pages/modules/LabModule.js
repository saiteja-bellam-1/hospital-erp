import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { normalizeUserRoles, canAccessLabAdminDashboard } from '../../hooks/useNavigationSections';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import {
  TestTube, Plus, Edit2, Trash2, Search, RefreshCw,
  Activity, ClipboardList, CheckCircle, Loader2, Database, Settings2, Package, Droplets
} from 'lucide-react';
import axios from 'axios';
import LabTestParametersPage from './LabTestParametersPage';

const LabModuleMain = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [stats, setStats] = useState(null);
  const [categories, setCategories] = useState([]);
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Category dialog
  const [showCategoryDialog, setShowCategoryDialog] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);
  const [categoryForm, setCategoryForm] = useState({ name: '', description: '' });

  // Sample Types
  const [sampleTypes, setSampleTypes] = useState([]);
  const [showSampleTypeDialog, setShowSampleTypeDialog] = useState(false);
  const [editingSampleType, setEditingSampleType] = useState(null);
  const [sampleTypeForm, setSampleTypeForm] = useState({ name: '', description: '' });

  // Test dialog
  const [showTestDialog, setShowTestDialog] = useState(false);
  const [editingTest, setEditingTest] = useState(null);
  const [testForm, setTestForm] = useState({
    test_code: '', name: '', description: '', category_id: '',
    cost: '', sample_type_id: '', method: '', preparation_instructions: ''
  });

  // Confirm dialog
  const [confirmState, setConfirmState] = useState({ open: false });
  const confirm = (message, onConfirm, title) =>
    setConfirmState({ open: true, message, onConfirm, title });

  // Seed loading
  const [seeding, setSeeding] = useState(false);

  // Package state
  const [packageCategories, setPackageCategories] = useState([]);
  const [packages, setPackages] = useState([]);
  const [pkgCategoryFilter, setPkgCategoryFilter] = useState('all');
  const [pkgSearch, setPkgSearch] = useState('');
  const [showPkgCategoryDialog, setShowPkgCategoryDialog] = useState(false);
  const [editingPkgCategory, setEditingPkgCategory] = useState(null);
  const [pkgCategoryForm, setPkgCategoryForm] = useState({ name: '', description: '' });
  const [showPackageDialog, setShowPackageDialog] = useState(false);
  const [editingPackage, setEditingPackage] = useState(null);
  const [packageForm, setPackageForm] = useState({
    package_code: '', name: '', description: '', category_id: '',
    package_price: '', test_ids: []
  });

  // Feedback
  const [feedback, setFeedback] = useState({ message: '', type: '' });

  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback({ message: '', type: '' }), 3000);
  };

  // ============ Data fetching ============

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }, []);

  const fetchCategories = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/categories');
      setCategories(res.data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  }, []);

  const fetchSampleTypes = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/sample-types');
      setSampleTypes(res.data);
    } catch (err) {
      console.error('Failed to fetch sample types:', err);
    }
  }, []);

  const fetchTests = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (categoryFilter !== 'all') params.category_id = categoryFilter;
      if (searchQuery) params.search = searchQuery;
      const res = await axios.get('/api/lab/tests', { params });
      setTests(res.data);
    } catch (err) {
      console.error('Failed to fetch tests:', err);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, searchQuery]);

  useEffect(() => {
    fetchStats();
    fetchCategories();
    fetchSampleTypes();
  }, [fetchStats, fetchCategories, fetchSampleTypes]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  // ============ Category CRUD ============

  const openCategoryDialog = (category = null) => {
    if (category) {
      setEditingCategory(category);
      setCategoryForm({ name: category.name, description: category.description || '' });
    } else {
      setEditingCategory(null);
      setCategoryForm({ name: '', description: '' });
    }
    setShowCategoryDialog(true);
  };

  const handleSaveCategory = async () => {
    if (!categoryForm.name.trim()) return;
    try {
      if (editingCategory) {
        await axios.put(`/api/lab/categories/${editingCategory.id}`, categoryForm);
        showFeedback('Category updated');
      } else {
        await axios.post('/api/lab/categories', categoryForm);
        showFeedback('Category created');
      }
      setShowCategoryDialog(false);
      fetchCategories();
      fetchTests();
      fetchStats();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save category', 'error');
    }
  };

  const handleDeleteCategory = (id) => {
    confirm('Delete this category? Tests in this category will not be deleted.', async () => {
      try {
        await axios.delete(`/api/lab/categories/${id}`);
        showFeedback('Category deleted');
        fetchCategories();
        fetchStats();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete category', 'error');
      }
    }, 'Delete Category');
  };

  // ============ Sample Type CRUD ============

  const openSampleTypeDialog = (st = null) => {
    if (st) {
      setEditingSampleType(st);
      setSampleTypeForm({ name: st.name, description: st.description || '' });
    } else {
      setEditingSampleType(null);
      setSampleTypeForm({ name: '', description: '' });
    }
    setShowSampleTypeDialog(true);
  };

  const handleSaveSampleType = async () => {
    if (!sampleTypeForm.name.trim()) return;
    try {
      if (editingSampleType) {
        await axios.put(`/api/lab/sample-types/${editingSampleType.id}`, sampleTypeForm);
        showFeedback('Sample type updated');
      } else {
        await axios.post('/api/lab/sample-types', sampleTypeForm);
        showFeedback('Sample type created');
      }
      setShowSampleTypeDialog(false);
      fetchSampleTypes();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save sample type', 'error');
    }
  };

  const handleDeleteSampleType = (id) => {
    confirm('Delete this sample type? Tests using it will not be deleted.', async () => {
      try {
        await axios.delete(`/api/lab/sample-types/${id}`);
        showFeedback('Sample type deleted');
        fetchSampleTypes();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete sample type', 'error');
      }
    }, 'Delete Sample Type');
  };

  // ============ Test CRUD ============

  const openTestDialog = (test = null) => {
    if (test) {
      setEditingTest(test);
      setTestForm({
        test_code: test.test_code, name: test.name,
        description: test.description || '', category_id: String(test.category_id),
        cost: String(test.cost), sample_type_id: test.sample_type_id ? String(test.sample_type_id) : '',
        method: test.method || '', preparation_instructions: test.preparation_instructions || ''
      });
    } else {
      setEditingTest(null);
      setTestForm({
        test_code: '', name: '', description: '', category_id: '',
        cost: '', sample_type_id: '', method: '', preparation_instructions: ''
      });
    }
    setShowTestDialog(true);
  };

  const handleSaveTest = async () => {
    if (!testForm.name.trim() || !testForm.test_code.trim() || !testForm.category_id || !testForm.cost) return;
    const payload = {
      ...testForm,
      category_id: parseInt(testForm.category_id),
      cost: parseFloat(testForm.cost),
      sample_type_id: testForm.sample_type_id ? parseInt(testForm.sample_type_id) : null,
    };
    try {
      if (editingTest) {
        await axios.put(`/api/lab/tests/${editingTest.id}`, payload);
        showFeedback('Test updated');
      } else {
        await axios.post('/api/lab/tests', payload);
        showFeedback('Test created');
      }
      setShowTestDialog(false);
      fetchTests();
      fetchStats();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save test', 'error');
    }
  };

  const handleDeleteTest = (id) => {
    confirm('Delete this test? This will deactivate the test.', async () => {
      try {
        await axios.delete(`/api/lab/tests/${id}`);
        showFeedback('Test deleted');
        fetchTests();
        fetchStats();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete test', 'error');
      }
    }, 'Delete Test');
  };

  // ============ Seed defaults ============

  const handleSeedDefaults = () => {
    confirm(
      'This will seed default lab tests (CBC, LFT, RFT, etc.) with standard parameters and reference ranges. Existing tests will not be duplicated. Continue?',
      async () => {
        setSeeding(true);
        try {
          const res = await axios.post('/api/lab/seed-defaults');
          showFeedback(res.data.message || 'Default tests seeded successfully');
          fetchTests();
          fetchCategories();
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

  // ============ Package Data Fetching ============

  const fetchPackageCategories = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/packages/categories');
      setPackageCategories(res.data);
    } catch (err) {
      console.error('Failed to fetch package categories:', err);
    }
  }, []);

  const fetchPackages = useCallback(async () => {
    try {
      const params = { active_only: false };
      if (pkgCategoryFilter !== 'all') params.category_id = pkgCategoryFilter;
      if (pkgSearch) params.search = pkgSearch;
      const res = await axios.get('/api/lab/packages', { params });
      setPackages(res.data);
    } catch (err) {
      console.error('Failed to fetch packages:', err);
    }
  }, [pkgCategoryFilter, pkgSearch]);

  useEffect(() => { fetchPackageCategories(); }, [fetchPackageCategories]);
  useEffect(() => { fetchPackages(); }, [fetchPackages]);

  // ============ Package Category CRUD ============

  const openPkgCategoryDialog = (cat = null) => {
    if (cat) {
      setEditingPkgCategory(cat);
      setPkgCategoryForm({ name: cat.name, description: cat.description || '' });
    } else {
      setEditingPkgCategory(null);
      setPkgCategoryForm({ name: '', description: '' });
    }
    setShowPkgCategoryDialog(true);
  };

  const handleSavePkgCategory = async () => {
    if (!pkgCategoryForm.name.trim()) return;
    try {
      if (editingPkgCategory) {
        await axios.put(`/api/lab/packages/categories/${editingPkgCategory.id}`, pkgCategoryForm);
        showFeedback('Package category updated');
      } else {
        await axios.post('/api/lab/packages/categories', pkgCategoryForm);
        showFeedback('Package category created');
      }
      setShowPkgCategoryDialog(false);
      fetchPackageCategories();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save package category', 'error');
    }
  };

  const handleDeletePkgCategory = (id) => {
    confirm('Deactivate this package category?', async () => {
      try {
        await axios.delete(`/api/lab/packages/categories/${id}`);
        showFeedback('Package category deactivated');
        fetchPackageCategories();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed', 'error');
      }
    }, 'Deactivate Category');
  };

  // ============ Package CRUD ============

  const openPackageDialog = (pkg = null) => {
    if (pkg) {
      setEditingPackage(pkg);
      setPackageForm({
        package_code: pkg.package_code, name: pkg.name,
        description: pkg.description || '', category_id: String(pkg.category_id),
        package_price: String(pkg.package_price),
        test_ids: pkg.tests.map(t => t.id)
      });
    } else {
      setEditingPackage(null);
      setPackageForm({
        package_code: '', name: '', description: '', category_id: '',
        package_price: '', test_ids: []
      });
    }
    setShowPackageDialog(true);
  };

  const handleSavePackage = async () => {
    if (!packageForm.name.trim() || !packageForm.package_code.trim() || !packageForm.category_id || !packageForm.package_price || packageForm.test_ids.length === 0) return;
    const payload = {
      package_code: packageForm.package_code,
      name: packageForm.name,
      description: packageForm.description,
      category_id: parseInt(packageForm.category_id),
      package_price: parseFloat(packageForm.package_price),
      test_ids: packageForm.test_ids,
    };
    try {
      if (editingPackage) {
        await axios.put(`/api/lab/packages/${editingPackage.id}`, payload);
        showFeedback('Package updated');
      } else {
        await axios.post('/api/lab/packages', payload);
        showFeedback('Package created');
      }
      setShowPackageDialog(false);
      fetchPackages();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save package', 'error');
    }
  };

  const handleDeletePackage = (id) => {
    confirm('Deactivate this package?', async () => {
      try {
        await axios.delete(`/api/lab/packages/${id}`);
        showFeedback('Package deactivated');
        fetchPackages();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed', 'error');
      }
    }, 'Deactivate Package');
  };

  const toggleTestInPackage = (testId) => {
    setPackageForm(prev => {
      const ids = prev.test_ids.includes(testId)
        ? prev.test_ids.filter(id => id !== testId)
        : [...prev.test_ids, testId];
      return { ...prev, test_ids: ids };
    });
  };

  const selectedTestsCost = packageForm.test_ids.reduce((sum, tid) => {
    const t = tests.find(tt => tt.id === tid);
    return sum + (t ? t.cost : 0);
  }, 0);

  // ============ Render helpers ============

  const renderFeedback = () => {
    if (!feedback.message) return null;
    return (
      <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white ${
        feedback.type === 'error' ? 'bg-red-500' : 'bg-green-500'
      }`}>
        {feedback.message}
      </div>
    );
  };

  // ============ Dashboard Tab ============

  const renderDashboard = () => (
    <div className="space-y-6">
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
          <CardTitle className="flex items-center justify-between">
            <span>Quick Actions</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => { setActiveTab('tests'); openTestDialog(); }}>
              <Plus className="h-4 w-4 mr-2" /> New Test
            </Button>
            <Button variant="outline" onClick={() => { setActiveTab('categories'); openCategoryDialog(); }}>
              <Plus className="h-4 w-4 mr-2" /> New Category
            </Button>
            <Button variant="outline" onClick={handleSeedDefaults} disabled={seeding}>
              {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Database className="h-4 w-4 mr-2" />}
              Seed Default Tests
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // ============ Categories Tab ============

  const renderCategories = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Test Categories</h2>
        <Button onClick={() => openCategoryDialog()}>
          <Plus className="h-4 w-4 mr-2" /> Add Category
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {categories.map(cat => (
          <Card key={cat.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{cat.name}</h3>
                  {cat.description && <p className="text-sm text-gray-500 mt-1">{cat.description}</p>}
                  <Badge variant="secondary" className="mt-2">{cat.test_count || 0} tests</Badge>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => openCategoryDialog(cat)}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDeleteCategory(cat.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {categories.length === 0 && (
          <div className="col-span-full text-center py-8 text-gray-500">
            No categories yet. Create one or seed defaults.
          </div>
        )}
      </div>
    </div>
  );

  // ============ Sample Types Tab ============

  const renderSampleTypes = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Sample Types</h2>
        <Button onClick={() => openSampleTypeDialog()}>
          <Plus className="h-4 w-4 mr-2" /> Add Sample Type
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {sampleTypes.map(st => (
          <Card key={st.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{st.name}</h3>
                  {st.description && <p className="text-sm text-gray-500 mt-1">{st.description}</p>}
                  <Badge variant="secondary" className="mt-2">{st.test_count || 0} tests</Badge>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => openSampleTypeDialog(st)}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDeleteSampleType(st.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {sampleTypes.length === 0 && (
          <div className="col-span-full text-center py-8 text-gray-500">
            No sample types yet. Add sample types like Blood, Urine, Serum, etc.
          </div>
        )}
      </div>
    </div>
  );

  const renderSampleTypeDialog = () => (
    <Dialog open={showSampleTypeDialog} onOpenChange={setShowSampleTypeDialog}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editingSampleType ? 'Edit Sample Type' : 'New Sample Type'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Sample Type Name *</Label>
            <Input value={sampleTypeForm.name}
              onChange={(e) => setSampleTypeForm({ ...sampleTypeForm, name: e.target.value })}
              placeholder="e.g. Blood, Urine, Serum" />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={sampleTypeForm.description}
              onChange={(e) => setSampleTypeForm({ ...sampleTypeForm, description: e.target.value })}
              placeholder="Optional description" rows={3} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowSampleTypeDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveSampleType} disabled={!sampleTypeForm.name.trim()}>
              {editingSampleType ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  // ============ Tests Tab ============

  const renderTests = () => (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex flex-col md:flex-row gap-3 flex-1">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search tests..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="All Categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              {categories.map(cat => (
                <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchTests}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => openTestDialog()}>
            <Plus className="h-4 w-4 mr-2" /> Add Test
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      ) : tests.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            No tests found. Create a test or seed defaults to get started.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {tests.map(test => (
            <Card key={test.id} className={!test.is_active ? 'opacity-60' : ''}>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{test.name}</span>
                      <Badge variant="outline" className="text-xs">{test.test_code}</Badge>
                      {!test.is_active && <Badge variant="destructive" className="text-xs">Inactive</Badge>}
                    </div>
                    <div className="flex items-center gap-3 text-sm text-gray-500 mt-1 flex-wrap">
                      <span>{test.category_name}</span>
                      <span>|</span>
                      <span>Rs. {test.cost}</span>
                      {test.sample_type_name && <><span>|</span><span>{test.sample_type_name}</span></>}
                      {test.method && <><span>|</span><span>{test.method}</span></>}
                      <span>|</span>
                      <span>{test.parameters?.length || 0} parameters</span>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="outline" size="sm" className="text-xs"
                      onClick={() => navigate(`/dashboard/lab/tests/${test.id}/parameters`)}>
                      <Settings2 className="h-3.5 w-3.5 mr-1.5" /> Parameters
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openTestDialog(test)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDeleteTest(test.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  // ============ Dialogs ============

  const renderCategoryDialog = () => (
    <Dialog open={showCategoryDialog} onOpenChange={setShowCategoryDialog}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editingCategory ? 'Edit Category' : 'New Category'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Category Name *</Label>
            <Input value={categoryForm.name}
              onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })}
              placeholder="e.g. Hematology" />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={categoryForm.description}
              onChange={(e) => setCategoryForm({ ...categoryForm, description: e.target.value })}
              placeholder="Optional description" rows={3} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowCategoryDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveCategory} disabled={!categoryForm.name.trim()}>
              {editingCategory ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  const renderTestDialog = () => (
    <Dialog open={showTestDialog} onOpenChange={setShowTestDialog}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editingTest ? 'Edit Test' : 'New Test'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Test Code *</Label>
              <Input value={testForm.test_code}
                onChange={(e) => setTestForm({ ...testForm, test_code: e.target.value })}
                placeholder="e.g. CBC" />
            </div>
            <div>
              <Label>Cost (Rs.) *</Label>
              <Input type="number" value={testForm.cost}
                onChange={(e) => setTestForm({ ...testForm, cost: e.target.value })}
                placeholder="0" />
            </div>
          </div>
          <div>
            <Label>Test Name *</Label>
            <Input value={testForm.name}
              onChange={(e) => setTestForm({ ...testForm, name: e.target.value })}
              placeholder="e.g. Complete Blood Count" />
          </div>
          <div>
            <Label>Category *</Label>
            <Select value={testForm.category_id} onValueChange={(v) => setTestForm({ ...testForm, category_id: v })}>
              <SelectTrigger>
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                {categories.map(cat => (
                  <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Sample Type</Label>
              <Select value={testForm.sample_type_id || 'none'} onValueChange={(v) => setTestForm({ ...testForm, sample_type_id: v === 'none' ? '' : v })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select sample type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {sampleTypes.map(st => (
                    <SelectItem key={st.id} value={String(st.id)}>{st.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Method</Label>
              <Input value={testForm.method}
                onChange={(e) => setTestForm({ ...testForm, method: e.target.value })}
                placeholder="e.g. Automated Analyzer, ELISA" />
            </div>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={testForm.description}
              onChange={(e) => setTestForm({ ...testForm, description: e.target.value })}
              placeholder="Optional description" rows={2} />
          </div>
          <div>
            <Label>Preparation Instructions</Label>
            <Textarea value={testForm.preparation_instructions}
              onChange={(e) => setTestForm({ ...testForm, preparation_instructions: e.target.value })}
              placeholder="e.g. Fasting for 12 hours" rows={2} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowTestDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveTest}
              disabled={!testForm.name.trim() || !testForm.test_code.trim() || !testForm.category_id || !testForm.cost}>
              {editingTest ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  // ============ Packages Tab ============

  const renderPackages = () => (
    <div className="space-y-6">
      {/* Package Categories */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Package Categories</h2>
          <Button size="sm" onClick={() => openPkgCategoryDialog()}>
            <Plus className="h-4 w-4 mr-2" /> Add Category
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {packageCategories.filter(c => c.is_active).map(cat => (
            <Card key={cat.id}>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold">{cat.name}</h3>
                    {cat.description && <p className="text-xs text-gray-500 mt-0.5">{cat.description}</p>}
                    <Badge variant="secondary" className="mt-1 text-xs">{cat.package_count || 0} packages</Badge>
                  </div>
                  <div className="flex gap-0.5">
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => openPkgCategoryDialog(cat)}>
                      <Edit2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500" onClick={() => handleDeletePkgCategory(cat.id)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
          {packageCategories.filter(c => c.is_active).length === 0 && (
            <div className="col-span-full text-center py-6 text-gray-500 text-sm">
              No package categories yet. Create one to get started.
            </div>
          )}
        </div>
      </div>

      {/* Package List */}
      <div>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 mb-3">
          <div className="flex flex-col md:flex-row gap-3 flex-1">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input placeholder="Search packages..." value={pkgSearch}
                onChange={(e) => setPkgSearch(e.target.value)} className="pl-10" />
            </div>
            <Select value={pkgCategoryFilter} onValueChange={setPkgCategoryFilter}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="All Categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {packageCategories.filter(c => c.is_active).map(cat => (
                  <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchPackages}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button onClick={() => openPackageDialog()}>
              <Plus className="h-4 w-4 mr-2" /> Add Package
            </Button>
          </div>
        </div>

        {packages.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-gray-500">
              No packages found. Create a package to bundle tests together.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {packages.map(pkg => (
              <Card key={pkg.id} className={!pkg.is_active ? 'opacity-60' : ''}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold">{pkg.name}</span>
                        <Badge variant="outline" className="text-xs">{pkg.package_code}</Badge>
                        {!pkg.is_active && <Badge variant="destructive" className="text-xs">Inactive</Badge>}
                        {pkg.discount_percentage > 0 && (
                          <Badge className="bg-green-100 text-green-700 text-xs">
                            {pkg.discount_percentage}% off
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-sm text-gray-500 mt-1 flex-wrap">
                        <span>{pkg.category_name}</span>
                        <span>|</span>
                        <span className="line-through text-gray-400">Rs. {pkg.actual_price}</span>
                        <span className="font-semibold text-gray-700">Rs. {pkg.package_price}</span>
                        <span>|</span>
                        <span>{pkg.tests.length} tests</span>
                      </div>
                      {pkg.description && <p className="text-xs text-gray-400 mt-1">{pkg.description}</p>}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {pkg.tests.map(t => (
                          <Badge key={t.id} variant="secondary" className="text-xs font-normal">
                            {t.name} (Rs.{t.cost})
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-1 ml-4">
                      <Button variant="ghost" size="sm" onClick={() => openPackageDialog(pkg)}>
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDeletePackage(pkg.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  // ============ Package Dialogs ============

  const renderPkgCategoryDialog = () => (
    <Dialog open={showPkgCategoryDialog} onOpenChange={setShowPkgCategoryDialog}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editingPkgCategory ? 'Edit Package Category' : 'New Package Category'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Category Name *</Label>
            <Input value={pkgCategoryForm.name}
              onChange={(e) => setPkgCategoryForm({ ...pkgCategoryForm, name: e.target.value })}
              placeholder="e.g. Health Checkup, Wellness" />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={pkgCategoryForm.description}
              onChange={(e) => setPkgCategoryForm({ ...pkgCategoryForm, description: e.target.value })}
              placeholder="Optional description" rows={3} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowPkgCategoryDialog(false)}>Cancel</Button>
            <Button onClick={handleSavePkgCategory} disabled={!pkgCategoryForm.name.trim()}>
              {editingPkgCategory ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  const renderPackageDialog = () => (
    <Dialog open={showPackageDialog} onOpenChange={setShowPackageDialog}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editingPackage ? 'Edit Package' : 'New Package'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 max-h-[75vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Package Code *</Label>
              <Input value={packageForm.package_code}
                onChange={(e) => setPackageForm({ ...packageForm, package_code: e.target.value })}
                placeholder="e.g. FBC-01" />
            </div>
            <div>
              <Label>Category *</Label>
              <Select value={packageForm.category_id} onValueChange={(v) => setPackageForm({ ...packageForm, category_id: v })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {packageCategories.filter(c => c.is_active).map(cat => (
                    <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Package Name *</Label>
            <Input value={packageForm.name}
              onChange={(e) => setPackageForm({ ...packageForm, name: e.target.value })}
              placeholder="e.g. Full Body Checkup" />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={packageForm.description}
              onChange={(e) => setPackageForm({ ...packageForm, description: e.target.value })}
              placeholder="Optional description" rows={2} />
          </div>

          {/* Test Selection */}
          <div>
            <Label className="mb-2 block">Select Tests * ({packageForm.test_ids.length} selected)</Label>
            <div className="border rounded-lg max-h-52 overflow-y-auto p-3 space-y-1">
              {categories.map(cat => {
                const catTests = tests.filter(t => t.category_id === cat.id && t.is_active);
                if (catTests.length === 0) return null;
                return (
                  <div key={cat.id} className="mb-2">
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{cat.name}</p>
                    {catTests.map(t => (
                      <label key={t.id} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-50 cursor-pointer">
                        <input type="checkbox"
                          checked={packageForm.test_ids.includes(t.id)}
                          onChange={() => toggleTestInPackage(t.id)}
                          className="rounded border-gray-300"
                        />
                        <span className="text-sm flex-1">{t.name}</span>
                        <span className="text-xs text-gray-400">{t.test_code}</span>
                        <span className="text-xs font-medium">Rs. {t.cost}</span>
                      </label>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Pricing */}
          <div className="grid grid-cols-3 gap-4 bg-gray-50 p-3 rounded-lg">
            <div>
              <Label className="text-xs text-gray-500">Actual Price (sum)</Label>
              <p className="text-lg font-bold">Rs. {selectedTestsCost.toFixed(2)}</p>
            </div>
            <div>
              <Label>Package Price (Rs.) *</Label>
              <Input type="number" value={packageForm.package_price}
                onChange={(e) => setPackageForm({ ...packageForm, package_price: e.target.value })}
                placeholder="0" />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Discount</Label>
              <p className="text-lg font-bold text-green-600">
                {selectedTestsCost > 0 && packageForm.package_price
                  ? `${((1 - parseFloat(packageForm.package_price || 0) / selectedTestsCost) * 100).toFixed(1)}%`
                  : '0%'}
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowPackageDialog(false)}>Cancel</Button>
            <Button onClick={handleSavePackage}
              disabled={!packageForm.name.trim() || !packageForm.package_code.trim() || !packageForm.category_id || !packageForm.package_price || packageForm.test_ids.length === 0}>
              {editingPackage ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  // ============ Main Render ============

  return (
    <div className="space-y-6">
      {renderFeedback()}

      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Laboratory Management</h1>
        <Button variant="outline" onClick={handleSeedDefaults} disabled={seeding}>
          {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Database className="h-4 w-4 mr-2" />}
          Seed Defaults
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="tests">Test Catalog</TabsTrigger>
          <TabsTrigger value="categories">Categories</TabsTrigger>
          <TabsTrigger value="sample_types">
            <Droplets className="h-4 w-4 mr-1.5" /> Sample Types
          </TabsTrigger>
          <TabsTrigger value="packages">
            <Package className="h-4 w-4 mr-1.5" /> Packages
          </TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">{renderDashboard()}</TabsContent>
        <TabsContent value="tests">{renderTests()}</TabsContent>
        <TabsContent value="categories">{renderCategories()}</TabsContent>
        <TabsContent value="sample_types">{renderSampleTypes()}</TabsContent>
        <TabsContent value="packages">{renderPackages()}</TabsContent>
      </Tabs>

      {renderCategoryDialog()}
      {renderTestDialog()}
      {renderSampleTypeDialog()}
      {renderPkgCategoryDialog()}
      {renderPackageDialog()}

      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        onConfirm={() => { confirmState.onConfirm?.(); setConfirmState({ open: false }); }}
        onCancel={() => setConfirmState({ open: false })}
      />
    </div>
  );
};

const LabAdminRouteGuard = ({ children }) => {
  const { user } = useAuth();
  if (!canAccessLabAdminDashboard(normalizeUserRoles(user))) {
    return <Navigate to="/dashboard/lab-home" replace />;
  }
  return children;
};

// Routing wrapper
const LabModule = () => {
  return (
    <LabAdminRouteGuard>
      <Routes>
        <Route path="/" element={<LabModuleMain />} />
        <Route path="/tests/:testId/parameters" element={<LabTestParametersPage />} />
      </Routes>
    </LabAdminRouteGuard>
  );
};

export default LabModule;
