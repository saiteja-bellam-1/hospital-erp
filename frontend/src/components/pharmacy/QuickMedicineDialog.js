import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import PharmacyMasterSelectWithCreate from './PharmacyMasterSelectWithCreate';

const BLANK = {
  medicine_code: '',
  name: '',
  category_id: null,
  mrp: 0,
  rate_a: 0,
  purchase_rate: 0,
};

/**
 * Minimal medicine quick-create for POS / purchase workflows.
 *
 * @param {object} [prefill] - { medicine_code?, name? }
 * @param {(medicine: object) => void} onCreated
 */
export default function QuickMedicineDialog({
  open,
  onOpenChange,
  prefill = {},
  onCreated,
  categories: controlledCategories,
  onCategoriesChange,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(BLANK);
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      ...BLANK,
      medicine_code: prefill.medicine_code || '',
      name: prefill.name || '',
    });
  }, [open, prefill]);

  useEffect(() => {
    if (controlledCategories != null) {
      setCategories(controlledCategories);
      return undefined;
    }
    let cancelled = false;
    axios.get('/api/pharmacy/categories').then((r) => {
      if (!cancelled) setCategories(r.data || []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [controlledCategories, open]);

  const setCategoriesList = (list) => {
    if (controlledCategories == null) setCategories(list);
    onCategoriesChange?.(list);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.medicine_code.trim() || !form.name.trim()) {
      toast({ variant: 'destructive', title: 'Code and name are required' });
      return;
    }
    if (!form.category_id) {
      toast({ variant: 'destructive', title: 'Category is required' });
      return;
    }
    setSaving(true);
    try {
      const payload = {
        medicine_code: form.medicine_code.trim(),
        name: form.name.trim(),
        category_id: form.category_id,
        mrp: parseFloat(form.mrp) || 0,
        rate_a: parseFloat(form.rate_a) || 0,
        purchase_rate: parseFloat(form.purchase_rate) || 0,
        unit_price: parseFloat(form.rate_a) || 0,
        is_active: true,
      };
      const res = await axios.post('/api/pharmacy/medicines', payload);
      toast({ title: 'Medicine created', description: res.data.name });
      onCreated?.(res.data);
      onOpenChange?.(false);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Create failed',
        description: errorDetail(err, 'Could not save medicine'),
      });
    } finally {
      setSaving(false);
    }
  };

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Medicine</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label className="text-xs">Code *</Label>
            <Input value={form.medicine_code} onChange={(e) => set('medicine_code', e.target.value)} />
          </div>
          <div>
            <Label className="text-xs">Name *</Label>
            <Input value={form.name} onChange={(e) => set('name', e.target.value)} />
          </div>
          <PharmacyMasterSelectWithCreate
            path="categories"
            label="Category *"
            value={form.category_id}
            onChange={(v) => set('category_id', v)}
            options={categories}
            onOptionsChange={setCategoriesList}
            placeholder="Pick category"
          />
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-xs">MRP</Label>
              <Input type="number" step="0.01" value={form.mrp}
                onChange={(e) => set('mrp', e.target.value === '' ? 0 : parseFloat(e.target.value))} />
            </div>
            <div>
              <Label className="text-xs">Rate A</Label>
              <Input type="number" step="0.01" value={form.rate_a}
                onChange={(e) => set('rate_a', e.target.value === '' ? 0 : parseFloat(e.target.value))} />
            </div>
            <div>
              <Label className="text-xs">P-Rate</Label>
              <Input type="number" step="0.01" value={form.purchase_rate}
                onChange={(e) => set('purchase_rate', e.target.value === '' ? 0 : parseFloat(e.target.value))} />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange?.(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Add & use'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
