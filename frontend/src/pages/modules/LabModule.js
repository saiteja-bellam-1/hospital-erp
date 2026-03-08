import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import {
  TestTube, Plus, Edit2, Trash2, Search, RefreshCw, ChevronDown, ChevronUp,
  Activity, ClipboardList, CheckCircle, AlertCircle, Loader2, Database, X
} from 'lucide-react';
import axios from 'axios';

const LabModule = () => {
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

  // Test dialog
  const [showTestDialog, setShowTestDialog] = useState(false);
  const [editingTest, setEditingTest] = useState(null);
  const [testForm, setTestForm] = useState({
    test_code: '', name: '', description: '', category_id: '',
    cost: '', sample_type: '', method: '', preparation_instructions: ''
  });

  // Parameter editor
  const [expandedTestId, setExpandedTestId] = useState(null);
  const [showParamDialog, setShowParamDialog] = useState(false);
  const [editingParam, setEditingParam] = useState(null);
  const [paramForm, setParamForm] = useState({
    parameter_name: '', unit: '', field_type: 'numeric',
    reference_min_male: '', reference_max_male: '',
    reference_min_female: '', reference_max_female: '',
    reference_min_default: '', reference_max_default: '',
    possible_values: '', display_order: 0
  });
  const [paramTestId, setParamTestId] = useState(null);
  const [genderSpecific, setGenderSpecific] = useState(false);

  // Seed loading
  const [seeding, setSeeding] = useState(false);

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
  }, [fetchStats, fetchCategories]);

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

  const handleDeleteCategory = async (id) => {
    if (!window.confirm('Delete this category? Tests in this category will not be deleted.')) return;
    try {
      await axios.delete(`/api/lab/categories/${id}`);
      showFeedback('Category deleted');
      fetchCategories();
      fetchStats();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to delete category', 'error');
    }
  };

  // ============ Test CRUD ============

  const openTestDialog = (test = null) => {
    if (test) {
      setEditingTest(test);
      setTestForm({
        test_code: test.test_code, name: test.name,
        description: test.description || '', category_id: String(test.category_id),
        cost: String(test.cost), sample_type: test.sample_type || '',
        method: test.method || '', preparation_instructions: test.preparation_instructions || ''
      });
    } else {
      setEditingTest(null);
      setTestForm({
        test_code: '', name: '', description: '', category_id: '',
        cost: '', sample_type: '', method: '', preparation_instructions: ''
      });
    }
    setShowTestDialog(true);
  };

  const handleSaveTest = async () => {
    if (!testForm.name.trim() || !testForm.test_code.trim() || !testForm.category_id || !testForm.cost) return;
    const payload = {
      ...testForm,
      category_id: parseInt(testForm.category_id),
      cost: parseFloat(testForm.cost)
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

  const handleDeleteTest = async (id) => {
    if (!window.confirm('Delete this test? This will deactivate the test.')) return;
    try {
      await axios.delete(`/api/lab/tests/${id}`);
      showFeedback('Test deleted');
      fetchTests();
      fetchStats();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to delete test', 'error');
    }
  };

  // ============ Parameter CRUD ============

  const openParamDialog = (testId, param = null) => {
    setParamTestId(testId);
    if (param) {
      setEditingParam(param);
      const hasGenderRanges = param.reference_min_male != null || param.reference_max_male != null ||
        param.reference_min_female != null || param.reference_max_female != null;
      setGenderSpecific(hasGenderRanges);
      setParamForm({
        parameter_name: param.parameter_name,
        unit: param.unit || '',
        field_type: param.field_type || 'numeric',
        reference_min_male: param.reference_min_male ?? '',
        reference_max_male: param.reference_max_male ?? '',
        reference_min_female: param.reference_min_female ?? '',
        reference_max_female: param.reference_max_female ?? '',
        reference_min_default: param.reference_min_default ?? '',
        reference_max_default: param.reference_max_default ?? '',
        possible_values: param.possible_values ? param.possible_values.join(', ') : '',
        display_order: param.display_order || 0
      });
    } else {
      setEditingParam(null);
      setGenderSpecific(false);
      setParamForm({
        parameter_name: '', unit: '', field_type: 'numeric',
        reference_min_male: '', reference_max_male: '',
        reference_min_female: '', reference_max_female: '',
        reference_min_default: '', reference_max_default: '',
        possible_values: '', display_order: 0
      });
    }
    setShowParamDialog(true);
  };

  const handleSaveParam = async () => {
    if (!paramForm.parameter_name.trim()) return;
    const payload = {
      parameter_name: paramForm.parameter_name,
      unit: paramForm.unit || null,
      field_type: paramForm.field_type,
      reference_min_male: genderSpecific && paramForm.reference_min_male !== '' ? parseFloat(paramForm.reference_min_male) : null,
      reference_max_male: genderSpecific && paramForm.reference_max_male !== '' ? parseFloat(paramForm.reference_max_male) : null,
      reference_min_female: genderSpecific && paramForm.reference_min_female !== '' ? parseFloat(paramForm.reference_min_female) : null,
      reference_max_female: genderSpecific && paramForm.reference_max_female !== '' ? parseFloat(paramForm.reference_max_female) : null,
      reference_min_default: paramForm.reference_min_default !== '' ? parseFloat(paramForm.reference_min_default) : null,
      reference_max_default: paramForm.reference_max_default !== '' ? parseFloat(paramForm.reference_max_default) : null,
      possible_values: paramForm.field_type === 'select' && paramForm.possible_values
        ? paramForm.possible_values.split(',').map(v => v.trim()).filter(Boolean)
        : null,
      display_order: parseInt(paramForm.display_order) || 0
    };
    try {
      if (editingParam) {
        await axios.put(`/api/lab/tests/${paramTestId}/parameters/${editingParam.id}`, payload);
        showFeedback('Parameter updated');
      } else {
        await axios.post(`/api/lab/tests/${paramTestId}/parameters`, payload);
        showFeedback('Parameter added');
      }
      setShowParamDialog(false);
      fetchTests();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save parameter', 'error');
    }
  };

  const handleDeleteParam = async (testId, paramId) => {
    if (!window.confirm('Delete this parameter?')) return;
    try {
      await axios.delete(`/api/lab/tests/${testId}/parameters/${paramId}`);
      showFeedback('Parameter deleted');
      fetchTests();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to delete parameter', 'error');
    }
  };

  // ============ Seed defaults ============

  const handleSeedDefaults = async () => {
    if (!window.confirm('This will seed default lab tests (CBC, LFT, RFT, etc.) with standard parameters and reference ranges. Existing tests will not be duplicated. Continue?')) return;
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
  };

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
                  <div className="flex items-center gap-4 flex-1 cursor-pointer"
                    onClick={() => setExpandedTestId(expandedTestId === test.id ? null : test.id)}>
                    <div className="flex items-center gap-2">
                      {expandedTestId === test.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{test.name}</span>
                          <Badge variant="outline" className="text-xs">{test.test_code}</Badge>
                          {!test.is_active && <Badge variant="destructive" className="text-xs">Inactive</Badge>}
                        </div>
                        <div className="flex items-center gap-3 text-sm text-gray-500 mt-1 flex-wrap">
                          <span>{test.category_name}</span>
                          <span>|</span>
                          <span>Rs. {test.cost}</span>
                          {test.sample_type && <><span>|</span><span>{test.sample_type}</span></>}
                          {test.method && <><span>|</span><span>{test.method}</span></>}
                          <span>|</span>
                          <span>{test.parameters?.length || 0} parameters</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openTestDialog(test)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDeleteTest(test.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {/* Expanded parameters */}
                {expandedTestId === test.id && (
                  <div className="mt-4 border-t pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-medium text-sm">Parameters</h4>
                      <Button size="sm" variant="outline" onClick={() => openParamDialog(test.id)}>
                        <Plus className="h-3 w-3 mr-1" /> Add Parameter
                      </Button>
                    </div>
                    {test.parameters && test.parameters.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-left text-gray-500">
                              <th className="pb-2 pr-4">#</th>
                              <th className="pb-2 pr-4">Parameter</th>
                              <th className="pb-2 pr-4">Unit</th>
                              <th className="pb-2 pr-4">Type</th>
                              <th className="pb-2 pr-4">Male Range</th>
                              <th className="pb-2 pr-4">Female Range</th>
                              <th className="pb-2 pr-4">Default Range</th>
                              <th className="pb-2">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {test.parameters.map((param, idx) => (
                              <tr key={param.id} className="border-b last:border-0">
                                <td className="py-2 pr-4 text-gray-400">{idx + 1}</td>
                                <td className="py-2 pr-4 font-medium">{param.parameter_name}</td>
                                <td className="py-2 pr-4">{param.unit || '-'}</td>
                                <td className="py-2 pr-4">
                                  <Badge variant="outline" className="text-xs">{param.field_type}</Badge>
                                </td>
                                <td className="py-2 pr-4">
                                  {param.reference_min_male != null || param.reference_max_male != null
                                    ? `${param.reference_min_male ?? '–'} - ${param.reference_max_male ?? '–'}`
                                    : '-'}
                                </td>
                                <td className="py-2 pr-4">
                                  {param.reference_min_female != null || param.reference_max_female != null
                                    ? `${param.reference_min_female ?? '–'} - ${param.reference_max_female ?? '–'}`
                                    : '-'}
                                </td>
                                <td className="py-2 pr-4">
                                  {param.reference_min_default != null || param.reference_max_default != null
                                    ? `${param.reference_min_default ?? '–'} - ${param.reference_max_default ?? '–'}`
                                    : '-'}
                                </td>
                                <td className="py-2">
                                  <div className="flex gap-1">
                                    <Button variant="ghost" size="sm" onClick={() => openParamDialog(test.id, param)}>
                                      <Edit2 className="h-3 w-3" />
                                    </Button>
                                    <Button variant="ghost" size="sm" className="text-red-500"
                                      onClick={() => handleDeleteParam(test.id, param.id)}>
                                      <Trash2 className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-sm text-gray-400 italic">No parameters configured. Add parameters to define what values lab technicians will enter.</p>
                    )}
                    {test.description && (
                      <p className="text-sm text-gray-500 mt-3"><strong>Description:</strong> {test.description}</p>
                    )}
                    {test.preparation_instructions && (
                      <p className="text-sm text-gray-500 mt-1"><strong>Preparation:</strong> {test.preparation_instructions}</p>
                    )}
                  </div>
                )}
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
              <Input value={testForm.sample_type}
                onChange={(e) => setTestForm({ ...testForm, sample_type: e.target.value })}
                placeholder="e.g. Blood, Urine, Serum" />
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

  const renderParamDialog = () => (
    <Dialog open={showParamDialog} onOpenChange={setShowParamDialog}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{editingParam ? 'Edit Parameter' : 'Add Parameter'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Parameter Name *</Label>
              <Input value={paramForm.parameter_name}
                onChange={(e) => setParamForm({ ...paramForm, parameter_name: e.target.value })}
                placeholder="e.g. Hemoglobin" />
            </div>
            <div>
              <Label>Unit</Label>
              <Input value={paramForm.unit}
                onChange={(e) => setParamForm({ ...paramForm, unit: e.target.value })}
                placeholder="e.g. g/dL, mg/dL" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Field Type</Label>
              <Select value={paramForm.field_type}
                onValueChange={(v) => setParamForm({ ...paramForm, field_type: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="numeric">Numeric</SelectItem>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="select">Select (Dropdown)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Order (sequence in report)</Label>
              <Input type="number" value={paramForm.display_order}
                onChange={(e) => setParamForm({ ...paramForm, display_order: e.target.value })}
                placeholder="e.g. 1, 2, 3..." />
            </div>
          </div>

          {paramForm.field_type === 'select' && (
            <div>
              <Label>Possible Values (comma-separated)</Label>
              <Input value={paramForm.possible_values}
                onChange={(e) => setParamForm({ ...paramForm, possible_values: e.target.value })}
                placeholder="e.g. Positive, Negative, Trace" />
            </div>
          )}

          {paramForm.field_type === 'numeric' && (
            <>
              <div className="border rounded-lg p-3 space-y-3">
                <h4 className="text-sm font-medium text-gray-700">Reference Range</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs">Min</Label>
                    <Input type="number" step="any" value={paramForm.reference_min_default}
                      onChange={(e) => setParamForm({ ...paramForm, reference_min_default: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">Max</Label>
                    <Input type="number" step="any" value={paramForm.reference_max_default}
                      onChange={(e) => setParamForm({ ...paramForm, reference_max_default: e.target.value })} />
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input type="checkbox" id="genderToggle" checked={genderSpecific}
                  onChange={(e) => setGenderSpecific(e.target.checked)}
                  className="rounded" />
                <Label htmlFor="genderToggle" className="text-sm cursor-pointer">
                  Enable gender-specific reference ranges
                </Label>
              </div>

              {genderSpecific && (
                <div className="space-y-3 pl-2 border-l-2 border-blue-200">
                  <div className="border rounded-lg p-3 space-y-3">
                    <h4 className="text-sm font-medium text-blue-700">Male Reference Range</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="text-xs">Min</Label>
                        <Input type="number" step="any" value={paramForm.reference_min_male}
                          onChange={(e) => setParamForm({ ...paramForm, reference_min_male: e.target.value })} />
                      </div>
                      <div>
                        <Label className="text-xs">Max</Label>
                        <Input type="number" step="any" value={paramForm.reference_max_male}
                          onChange={(e) => setParamForm({ ...paramForm, reference_max_male: e.target.value })} />
                      </div>
                    </div>
                  </div>

                  <div className="border rounded-lg p-3 space-y-3">
                    <h4 className="text-sm font-medium text-pink-700">Female Reference Range</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="text-xs">Min</Label>
                        <Input type="number" step="any" value={paramForm.reference_min_female}
                          onChange={(e) => setParamForm({ ...paramForm, reference_min_female: e.target.value })} />
                      </div>
                      <div>
                        <Label className="text-xs">Max</Label>
                        <Input type="number" step="any" value={paramForm.reference_max_female}
                          onChange={(e) => setParamForm({ ...paramForm, reference_max_female: e.target.value })} />
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-gray-400">
                    When gender-specific ranges are set, they take priority over the default range for that gender.
                  </p>
                </div>
              )}
            </>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowParamDialog(false)}>Cancel</Button>
            <Button onClick={handleSaveParam} disabled={!paramForm.parameter_name.trim()}>
              {editingParam ? 'Update' : 'Add'}
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
        </TabsList>

        <TabsContent value="dashboard">{renderDashboard()}</TabsContent>
        <TabsContent value="tests">{renderTests()}</TabsContent>
        <TabsContent value="categories">{renderCategories()}</TabsContent>
      </Tabs>

      {renderCategoryDialog()}
      {renderTestDialog()}
      {renderParamDialog()}
    </div>
  );
};

export default LabModule;
