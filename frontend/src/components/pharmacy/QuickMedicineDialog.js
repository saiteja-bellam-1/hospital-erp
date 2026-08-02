import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import { usePharmacyMedicineMasters } from '../../hooks/usePharmacyMedicineMasters';
import PharmacyFormDialog from './PharmacyFormDialog';
import MedicineFormFields, {
  EMPTY_MEDICINE_FORM,
  MEDICINE_FORM_STEPS,
  medicineStepCanProceed,
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
  const [activeStep, setActiveStep] = useState(0);
  const { masters, setMasters, loading } = usePharmacyMedicineMasters(open);

  useEffect(() => {
    if (!open) return;
    setActiveStep(0);
    setForm(patchMedicineForm(EMPTY_MEDICINE_FORM, {
      medicine_code: prefill.medicine_code || '',
      name: prefill.name || '',
    }));
  }, [open, prefill]);

  const steps = useMemo(
    () => MEDICINE_FORM_STEPS.map((s, i) => ({ ...s, completed: i < activeStep })),
    [activeStep],
  );

  const handleNext = () => {
    if (!medicineStepCanProceed(form, activeStep)) {
      toast({ variant: 'destructive', title: 'Code, name, and category are required' });
      return;
    }
    setActiveStep((s) => Math.min(s + 1, MEDICINE_FORM_STEPS.length - 1));
  };

  const handleSave = async () => {
    if (!medicineStepCanProceed(form, 0)) {
      toast({ variant: 'destructive', title: 'Code, name, and category are required' });
      setActiveStep(0);
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
    <PharmacyFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add Medicine"
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onNext={handleNext}
      onSave={handleSave}
      saving={saving}
      loading={loading}
      canProceed={activeStep !== 0 || medicineStepCanProceed(form, 0)}
      saveLabel="Add & use"
    >
      <MedicineFormFields
        form={form}
        onChange={setForm}
        masters={masters}
        onMastersChange={setMasters}
        activeStep={activeStep}
      />
    </PharmacyFormDialog>
  );
}
