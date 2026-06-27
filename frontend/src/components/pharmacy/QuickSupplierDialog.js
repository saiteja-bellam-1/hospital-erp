import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import SupplierFormFields, { EMPTY_SUPPLIER_FORM, prepareSupplierPayload } from './SupplierFormFields';

export default function QuickSupplierDialog({
  open,
  onOpenChange,
  prefill = {},
  onCreated,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(EMPTY_SUPPLIER_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY_SUPPLIER_FORM, ...prefill });
  }, [open, prefill]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name?.trim()) {
      toast({ variant: 'destructive', title: 'Ledger name is required' });
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/api/pharmacy/suppliers', prepareSupplierPayload(form));
      toast({ title: 'Supplier created', description: res.data.name });
      onCreated?.(res.data);
      onOpenChange?.(false);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Create failed',
        description: errorDetail(err, 'Could not save supplier'),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[88vh] overflow-y-auto" formNav="grid">
        <DialogHeader>
          <DialogTitle>Add Supplier</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <SupplierFormFields form={form} onChange={setForm} />
          <DialogFooter className="gap-2 sm:gap-0 pt-3">
            <Button type="button" variant="outline" onClick={() => onOpenChange?.(false)}>Cancel</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Add & select'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
