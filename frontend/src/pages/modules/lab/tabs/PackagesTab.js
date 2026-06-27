import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Plus, Edit2, Trash2, Search, RefreshCw } from 'lucide-react';
import { useLabFeedback } from '../useLabFeedback';

export default function PackagesTab() {
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [categories, setCategories] = useState([]);
  const [tests, setTests] = useState([]);
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
    package_price: '', test_ids: [],
  });

  const fetchCategories = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/categories');
      setCategories(res.data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  }, []);

  const fetchTests = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/tests');
      setTests(res.data);
    } catch (err) {
      console.error('Failed to fetch tests:', err);
    }
  }, []);

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

  useEffect(() => {
    fetchCategories();
    fetchTests();
    fetchPackageCategories();
  }, [fetchCategories, fetchTests, fetchPackageCategories]);

  useEffect(() => { fetchPackages(); }, [fetchPackages]);

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

  const openPackageDialog = (pkg = null) => {
    if (pkg) {
      setEditingPackage(pkg);
      setPackageForm({
        package_code: pkg.package_code, name: pkg.name,
        description: pkg.description || '', category_id: String(pkg.category_id),
        package_price: String(pkg.package_price),
        test_ids: pkg.tests.map(t => t.id),
      });
    } else {
      setEditingPackage(null);
      setPackageForm({
        package_code: '', name: '', description: '', category_id: '',
        package_price: '', test_ids: [],
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

  return (
    <div className="space-y-6">
      <FeedbackToast />

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

      <ConfirmDialogEl />
    </div>
  );
}
