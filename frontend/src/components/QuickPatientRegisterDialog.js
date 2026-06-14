import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2 } from 'lucide-react';
import { useToast } from '../hooks/use-toast';
import { errorDetail } from '../utils/apiErrors';

const BLANK = {
  first_name: '',
  last_name: '',
  primary_phone: '',
  age: '',
  date_of_birth: '',
  gender: '',
};

export default function QuickPatientRegisterDialog({
  open,
  onOpenChange,
  initialValues = {},
  onCreated,
}) {
  const { toast } = useToast();
  const [form, setForm] = useState(BLANK);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ ...BLANK, ...initialValues });
    }
  }, [open, initialValues]);

  const set = (key, val) => setForm((prev) => ({ ...prev, [key]: val }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.first_name?.trim() || !form.last_name?.trim() || !form.primary_phone?.trim()) {
      toast({
        variant: 'destructive',
        title: 'Missing fields',
        description: 'First name, last name, and phone are required.',
      });
      return;
    }
    if (!form.age && !form.date_of_birth) {
      toast({
        variant: 'destructive',
        title: 'Age required',
        description: 'Enter age or date of birth.',
      });
      return;
    }

    setSaving(true);
    try {
      const payload = Object.fromEntries(
        Object.entries({
          ...form,
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          primary_phone: form.primary_phone.trim(),
          age: form.age ? parseInt(form.age, 10) : null,
          date_of_birth: form.date_of_birth || null,
          gender: form.gender || null,
        }).map(([k, v]) => [k, v === '' ? null : v])
      );
      const res = await axios.post('/api/patients/', payload);
      toast({ title: 'Patient registered', description: `${res.data.first_name} ${res.data.last_name} added.` });
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
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Register New Patient</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="qp-first">First name *</Label>
              <Input id="qp-first" value={form.first_name} onChange={(e) => set('first_name', e.target.value)} required />
            </div>
            <div>
              <Label htmlFor="qp-last">Last name *</Label>
              <Input id="qp-last" value={form.last_name} onChange={(e) => set('last_name', e.target.value)} required />
            </div>
          </div>
          <div>
            <Label htmlFor="qp-phone">Phone *</Label>
            <Input id="qp-phone" value={form.primary_phone} onChange={(e) => set('primary_phone', e.target.value)} placeholder="10-digit mobile" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="qp-age">Age (years) *</Label>
              <Input
                id="qp-age"
                type="number"
                min="0"
                max="150"
                value={form.age}
                onChange={(e) => set('age', e.target.value)}
                placeholder="Years"
              />
            </div>
            <div>
              <Label htmlFor="qp-dob">Date of birth</Label>
              <Input
                id="qp-dob"
                type="date"
                value={form.date_of_birth}
                onChange={(e) => {
                  const dob = e.target.value;
                  set('date_of_birth', dob);
                  if (dob) {
                    const today = new Date();
                    const birth = new Date(dob);
                    let calcAge = today.getFullYear() - birth.getFullYear();
                    if (today.getMonth() < birth.getMonth()
                      || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) {
                      calcAge -= 1;
                    }
                    set('age', calcAge >= 0 ? String(calcAge) : '');
                  }
                }}
              />
            </div>
          </div>
          <div>
            <Label>Gender</Label>
            <Select value={form.gender || ''} onValueChange={(v) => set('gender', v)}>
              <SelectTrigger><SelectValue placeholder="Select gender" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="Male">Male</SelectItem>
                <SelectItem value="Female">Female</SelectItem>
                <SelectItem value="Other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={saving}>
              {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Register & select'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
