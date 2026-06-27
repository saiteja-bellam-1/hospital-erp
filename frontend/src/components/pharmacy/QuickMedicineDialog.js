import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import { usePharmacyMedicineMasters } from '../../hooks/usePharmacyMedicineMasters';
import MedicineFormFields, {
  EMPTY_MEDICINE_FORM,
  patchMedicineForm,
  prepareMedicinePayload,
} from './MedicineFormFields';

/**
 * Full medicine create dialog for POS / purchase workflows.
 *
 * @param {object} [prefill] - { medicine_code?, name? }
 * @param {(medicine: object) => void} onCreated
 */
export default function QuickMedicineDialog({
  open,
  onOpenChange,
  prefill = {},
  onCreated,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(EMPTY_MEDICINE_FORM);
  const [saving, setSaving] = useState(false);
  const { masters, setMasters, loading } = usePharmacyMedicineMasters(open);

  useEffect(() => {
    if (!open) return;
    setForm(patchMedicineForm(EMPTY_MEDICINE_FORM, {
      medicine_code: prefill.medicine_code || '',
      name: prefill.name || '',
    }));
  }, [open, prefill]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.medicine_code?.trim() || !form.name?.trim()) {
      toast({ variant: 'destructive', title: 'Code and name are required' });
      return;
    }
    if (!form.category_id) {
      toast({ variant: 'destructive', title: 'Category is required' });
      return;
    }
    setSaving(true);
    try {
      const payload = prepareMedicinePayload(form);
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" formNav="grid">
        <DialogHeader>
          <DialogTitle>Add Medicine</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading form…
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <MedicineFormFields
              form={form}
              onChange={setForm}
              masters={masters}
              onMastersChange={setMasters}
            />
            <DialogFooter className="gap-2 sm:gap-0 pt-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange?.(false)}>Cancel</Button>
              <Button type="submit" disabled={saving}>
                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Add & use'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
