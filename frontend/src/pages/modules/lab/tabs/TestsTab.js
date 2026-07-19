import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Plus, Edit2, Trash2, Search, RefreshCw, Settings2, Loader2, Upload, TestTube } from 'lucide-react';
import { useLabFeedback } from '../useLabFeedback';
import LabTestImportDialog from '../LabTestImportDialog';

export default function TestsTab() {
  const navigate = useNavigate();
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [categories, setCategories] = useState([]);
  const [sampleTypes, setSampleTypes] = useState([]);
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [showDialog, setShowDialog] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    test_code: '', name: '', description: '', category_id: '',
    cost: '', sample_type_id: '', method: '', preparation_instructions: '',
  });

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
    fetchCategories();
    fetchSampleTypes();
  }, [fetchCategories, fetchSampleTypes]);

  useEffect(() => { fetchTests(); }, [fetchTests]);

  const openDialog = (test = null) => {
    if (test) {
      setEditing(test);
      setForm({
        test_code: test.test_code, name: test.name,
        description: test.description || '', category_id: String(test.category_id),
        cost: String(test.cost), sample_type_id: test.sample_type_id ? String(test.sample_type_id) : '',
        method: test.method || '', preparation_instructions: test.preparation_instructions || '',
      });
    } else {
      setEditing(null);
      setForm({
        test_code: '', name: '', description: '', category_id: '',
        cost: '', sample_type_id: '', method: '', preparation_instructions: '',
      });
    }
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.test_code.trim() || !form.category_id || !form.cost) return;
    const payload = {
      ...form,
      category_id: parseInt(form.category_id),
      cost: parseFloat(form.cost),
      sample_type_id: form.sample_type_id ? parseInt(form.sample_type_id) : null,
    };
    try {
      if (editing) {
        await axios.put(`/api/lab/tests/${editing.id}`, payload);
        showFeedback('Test updated');
      } else {
        await axios.post('/api/lab/tests', payload);
        showFeedback('Test created');
      }
      setShowDialog(false);
      fetchTests();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save test', 'error');
    }
  };

  const handleDelete = (id) => {
    confirm('Delete this test? This will deactivate the test.', async () => {
      try {
        await axios.delete(`/api/lab/tests/${id}`);
        showFeedback('Test deleted');
        fetchTests();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete test', 'error');
      }
    }, 'Delete Test');
  };

  return (
    <div className="space-y-4">
      <FeedbackToast />

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
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4 mr-2" /> Import
          </Button>
          <Button onClick={() => openDialog()}>
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
          <CardContent className="py-12 text-center">
            <TestTube className="h-12 w-12 text-slate-200 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-600">No lab tests yet</p>
            <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
              Setting up your lab? Import your entire test list at once from an Excel or CSV file,
              or add tests one by one.
            </p>
            <div className="flex items-center justify-center gap-2 mt-4">
              <Button onClick={() => setShowImport(true)}>
                <Upload className="h-4 w-4 mr-2" /> Import Tests
              </Button>
              <Button variant="outline" onClick={() => openDialog()}>
                <Plus className="h-4 w-4 mr-2" /> Add Test
              </Button>
            </div>
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
                    <Button variant="ghost" size="sm" onClick={() => openDialog(test)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(test.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Test' : 'New Test'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Test Code *</Label>
                <Input value={form.test_code}
                  onChange={(e) => setForm({ ...form, test_code: e.target.value })}
                  placeholder="e.g. CBC" />
              </div>
              <div>
                <Label>Cost (Rs.) *</Label>
                <Input type="number" value={form.cost}
                  onChange={(e) => setForm({ ...form, cost: e.target.value })}
                  placeholder="0" />
              </div>
            </div>
            <div>
              <Label>Test Name *</Label>
              <Input value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Complete Blood Count" />
            </div>
            <div>
              <Label>Category *</Label>
              <Select value={form.category_id} onValueChange={(v) => setForm({ ...form, category_id: v })}>
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
                <Select value={form.sample_type_id || 'none'} onValueChange={(v) => setForm({ ...form, sample_type_id: v === 'none' ? '' : v })}>
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
                <Input value={form.method}
                  onChange={(e) => setForm({ ...form, method: e.target.value })}
                  placeholder="e.g. Automated Analyzer, ELISA" />
              </div>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional description" rows={2} />
            </div>
            <div>
              <Label>Preparation Instructions</Label>
              <Textarea value={form.preparation_instructions}
                onChange={(e) => setForm({ ...form, preparation_instructions: e.target.value })}
                placeholder="e.g. Fasting for 12 hours" rows={2} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
              <Button onClick={handleSave}
                disabled={!form.name.trim() || !form.test_code.trim() || !form.category_id || !form.cost}>
                {editing ? 'Update' : 'Create'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <LabTestImportDialog
        open={showImport}
        onOpenChange={setShowImport}
        onImported={() => { fetchTests(); fetchCategories(); fetchSampleTypes(); }}
        showFeedback={showFeedback}
      />

      <ConfirmDialogEl />
    </div>
  );
}
