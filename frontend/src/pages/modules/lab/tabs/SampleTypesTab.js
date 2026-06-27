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

export default function SampleTypesTab() {
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [sampleTypes, setSampleTypes] = useState([]);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', description: '' });

  const fetchSampleTypes = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/sample-types');
      setSampleTypes(res.data);
    } catch (err) {
      console.error('Failed to fetch sample types:', err);
    }
  }, []);

  useEffect(() => { fetchSampleTypes(); }, [fetchSampleTypes]);

  const openDialog = (st = null) => {
    if (st) {
      setEditing(st);
      setForm({ name: st.name, description: st.description || '' });
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
        await axios.put(`/api/lab/sample-types/${editing.id}`, form);
        showFeedback('Sample type updated');
      } else {
        await axios.post('/api/lab/sample-types', form);
        showFeedback('Sample type created');
      }
      setShowDialog(false);
      fetchSampleTypes();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to save sample type', 'error');
    }
  };

  const handleDelete = (id) => {
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

  return (
    <div className="space-y-4">
      <FeedbackToast />

      <div className="flex items-center justify-end">
        <Button onClick={() => openDialog()}>
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
                  <Button variant="ghost" size="sm" onClick={() => openDialog(st)}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(st.id)}>
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

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Sample Type' : 'New Sample Type'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Sample Type Name *</Label>
              <Input value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Blood, Urine, Serum" />
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
