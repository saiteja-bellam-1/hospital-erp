import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useToast } from '../hooks/use-toast';
import { errorDetail } from '../utils/apiErrors';
import SteppedFormDialog from './SteppedFormDialog';
import PatientRegisterFormFields, {
  EMPTY_PATIENT_FORM,
  PATIENT_FORM_STEPS,
  buildPatientPayload,
  patientStepCanProceed,
  validatePatientForm,
} from './PatientRegisterFormFields';

export default function QuickPatientRegisterDialog({
  open,
  onOpenChange,
  initialValues = {},
  onCreated,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(EMPTY_PATIENT_FORM);
  const [saving, setSaving] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (!open) return;
    setActiveStep(0);
    setForm({ ...EMPTY_PATIENT_FORM, ...initialValues });
  }, [open, initialValues]);

  const steps = useMemo(
    () => PATIENT_FORM_STEPS.map((s, i) => ({ ...s, completed: i < activeStep })),
    [activeStep],
  );

  const handleNext = () => {
    const err = validatePatientForm(form);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      return;
    }
    setActiveStep((s) => Math.min(s + 1, PATIENT_FORM_STEPS.length - 1));
  };

  const handleSave = async () => {
    const err = validatePatientForm(form);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      setActiveStep(0);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPatientPayload(form);
      const res = await axios.post('/api/patients/', payload);
      toast({
        title: 'Patient registered',
        description: `${res.data.first_name} ${res.data.last_name} added.`,
      });
      onCreated?.(res.data);
      onOpenChange(false);
    } catch (e) {
      toast({
        variant: 'destructive',
        title: 'Registration failed',
        description: errorDetail(e, 'Could not register patient'),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <SteppedFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Register New Patient"
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onNext={handleNext}
      onSave={handleSave}
      saving={saving}
      canProceed={activeStep !== 0 || patientStepCanProceed(form, 0)}
      saveLabel="Register & select"
    >
      <PatientRegisterFormFields form={form} onChange={setForm} activeStep={activeStep} />
    </SteppedFormDialog>
  );
}
