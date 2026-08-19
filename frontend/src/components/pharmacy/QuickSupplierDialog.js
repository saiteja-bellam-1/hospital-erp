import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import PharmacyFormDialog from './PharmacyFormDialog';
import SupplierFormFields, {
  EMPTY_SUPPLIER_FORM,
  SUPPLIER_FORM_STEPS,
  prepareSupplierPayload,
  supplierStepCanProceed,
} from './SupplierFormFields';

const NO_PREFILL = {};

export default function QuickSupplierDialog({
  open,
  onOpenChange,
  prefill = NO_PREFILL,
  onCreated,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(EMPTY_SUPPLIER_FORM);
  const [saving, setSaving] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (!open) return;
    setActiveStep(0);
    setForm({ ...EMPTY_SUPPLIER_FORM, ...prefill });
    // Reset only when the dialog opens. `prefill = {}` is a new object every
    // render, so depending on it wipes Ledger Name (and every other field)
    // after each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const steps = useMemo(
    () => SUPPLIER_FORM_STEPS.map((s, i) => ({ ...s, completed: i < activeStep })),
    [activeStep],
  );

  const handleNext = () => {
    if (!supplierStepCanProceed(form, activeStep)) {
      toast({ variant: 'destructive', title: 'Ledger name is required' });
      return;
    }
    setActiveStep((s) => Math.min(s + 1, SUPPLIER_FORM_STEPS.length - 1));
  };

  const handleSave = async () => {
    if (!supplierStepCanProceed(form, 0)) {
      toast({ variant: 'destructive', title: 'Ledger name is required' });
      setActiveStep(0);
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
    <PharmacyFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add Supplier"
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onNext={handleNext}
      onSave={handleSave}
      saving={saving}
      canProceed={activeStep !== 0 || supplierStepCanProceed(form, 0)}
      saveLabel="Add & select"
    >
      <SupplierFormFields form={form} onChange={setForm} activeStep={activeStep} />
    </PharmacyFormDialog>
  );
}
