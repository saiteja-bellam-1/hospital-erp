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
 * @param {object} [prefill] - { medicine_code?, name?, packaging?, pack_size?,
 *   manufacturer?, mrp?, purchase_rate?, rate_a?, rate_b?, strip_conversion_factor? }
 * @param {boolean} [lockName] - keep the catalog name equal to the import line
 * @param {(medicine: object) => void} onCreated
 */
const NO_PREFILL = {};

export default function QuickMedicineDialog({
  open,
  onOpenChange,
  prefill = NO_PREFILL,
  lockName = false,
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
    const name = prefill.name || '';
    const mrp = prefill.mrp ?? '';
    const vendorCode = String(prefill.medicine_code || '').trim();
    setForm(patchMedicineForm(EMPTY_MEDICINE_FORM, {
      medicine_code: vendorCode && vendorCode.length <= 20
        ? vendorCode
        : (name ? suggestMedicineCode(name) : ''),
      name,
      packaging: prefill.packaging || prefill.pack_size || '',
      manufacturer: prefill.manufacturer || '',
      mrp,
      purchase_rate: prefill.purchase_rate ?? '',
      rate_a: prefill.rate_a ?? mrp,
      rate_b: prefill.rate_b ?? mrp,
      strip_conversion_factor: prefill.strip_conversion_factor || 1,
    }));
    // Reset only when the dialog opens — a default `prefill = {}` is a new
    // object every render and would wipe typed fields after each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

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
      title={prefill.name ? `Add medicine — ${prefill.name}` : 'Add Medicine'}
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onNext={handleNext}
      onSave={handleSave}
      saving={saving}
      loading={loading}
      canProceed={activeStep !== 0 || medicineStepCanProceed(form, 0)}
      saveLabel={lockName ? 'Add to catalog' : 'Add & use'}
    >
      <MedicineFormFields
        form={form}
        onChange={setForm}
        masters={masters}
        onMastersChange={setMasters}
        activeStep={activeStep}
        nameReadOnly={lockName}
      />
    </PharmacyFormDialog>
  );
}

function suggestMedicineCode(name) {
  const base = String(name || 'MED').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12) || 'MED';
  return base.slice(0, 20);
}
