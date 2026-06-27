import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Plus, Edit2, Trash2 } from 'lucide-react';
import { useLabFeedback } from '../useLabFeedback';

export default function CategoriesTab() {
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [categories, setCategories] = useState([]);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', description: '' });

  const fetchCategories = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/categories');
      setCategories(res.data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  }, []);

  useEffect(() => { fetchCategories(); }, [fetchCategories]);

  const openDialog = (category = null) => {
    if (category) {
      setEditing(category);
      setForm({ name: category.name, description: category.description || '' });
    } else {
      setEditing(null);
      setForm({ name: '', description: '' });
    }
    setShowDialog(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    try {
      if (editing) {
        await axios.put(`/api/lab/categories/${editing.id}`, form);
        showFeedback('Category updated');
      } else {
        await axios.post('/api/lab/categories', form);
        showFeedback('Category created');
      }
      setShowDialog(false);
      fetchCategories();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save category', 'error');
    }
  };

  const handleDelete = (id) => {
    confirm('Delete this category? Tests in this category will not be deleted.', async () => {
      try {
        await axios.delete(`/api/lab/categories/${id}`);
        showFeedback('Category deleted');
        fetchCategories();
      } catch (err) {
        showFeedback(err.response?.data?.detail || 'Failed to delete category', 'error');
      }
    }, 'Delete Category');
  };

  return (
    <div className="space-y-4">
      <FeedbackToast />

      <div className="flex items-center justify-end">
        <Button onClick={() => openDialog()}>
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
                  <Button variant="ghost" size="sm" onClick={() => openDialog(cat)}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(cat.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {categories.length === 0 && (
          <div className="col-span-full text-center py-8 text-gray-500">
            No categories yet. Create one or seed defaults from the Dashboard.
          </div>
        )}
      </div>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Category' : 'New Category'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Category Name *</Label>
              <Input value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Hematology" />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Optional description" rows={3} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
              <Button onClick={handleSave} disabled={!form.name.trim()}>
                {editing ? 'Update' : 'Create'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialogEl />
    </div>
  );
}
