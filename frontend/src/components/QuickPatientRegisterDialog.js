import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Loader2 } from 'lucide-react';
import { useToast } from '../hooks/use-toast';
import { errorDetail } from '../utils/apiErrors';
import PatientRegisterFormFields, {
  EMPTY_PATIENT_FORM,
  buildPatientPayload,
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

  useEffect(() => {
    if (open) {
      setForm({ ...EMPTY_PATIENT_FORM, ...initialValues });
    }
  }, [open, initialValues]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const validationErr = validatePatientForm(form);
    if (validationErr) {
      toast({ variant: 'destructive', title: 'Missing fields', description: validationErr });
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
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Registration failed',
        description: errorDetail(err, 'Could not register patient'),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[98vw] max-w-7xl max-h-[95vh] flex flex-col gap-3 p-4 overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle>Register New Patient</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 gap-3">
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            <PatientRegisterFormFields form={form} onChange={setForm} />
          </div>
          <div className="flex gap-2 pt-2 border-t shrink-0">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={saving}>
              {saving
                ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</>
                : 'Register & select'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
