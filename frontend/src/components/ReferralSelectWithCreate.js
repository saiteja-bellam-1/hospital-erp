import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { UserPlus, Loader2 } from 'lucide-react';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from './ui/dialog';
import { useToast } from '../hooks/use-toast';
import { errorDetail } from '../utils/apiErrors';

const NONE = '_none';

async function fetchReferralsList() {
  try {
    const res = await axios.get('/api/referrals');
    return res.data || [];
  } catch {
    return [];
  }
}

/**
 * Referral dropdown with inline quick-create.
 *
 * @param {string} value - Referral name (empty = self/none)
 * @param {(name: string) => void} onValueChange
 * @param {object[]} [referrals] - Controlled list; fetched internally when omitted
 * @param {(list: object[]) => void} [onReferralsChange]
 */
export default function ReferralSelectWithCreate({
  value = '',
  onValueChange,
  referrals: controlledReferrals,
  onReferralsChange,
  label = 'Referred By',
  className = '',
}) {
  const { toast } = useToast();
  const [internalReferrals, setInternalReferrals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', village: '', mandal: '', district: '' });

  const referrals = controlledReferrals ?? internalReferrals;
  const setReferrals = (list) => {
    if (controlledReferrals == null) setInternalReferrals(list);
    onReferralsChange?.(list);
  };

  useEffect(() => {
    if (controlledReferrals != null) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      const list = await fetchReferralsList();
      if (!cancelled) {
        setInternalReferrals(list);
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [controlledReferrals]);

  const openCreate = () => {
    setForm({ name: '', phone: '', village: '', mandal: '', district: '' });
    setDialogOpen(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast({ variant: 'destructive', title: 'Name required', description: 'Enter the referral name.' });
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/api/referrals', {
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        village: form.village.trim() || null,
        mandal: form.mandal.trim() || null,
        district: form.district.trim() || null,
      });
      const next = [...referrals, res.data].sort((a, b) => a.name.localeCompare(b.name));
      setReferrals(next);
      onValueChange?.(res.data.name);
      toast({ title: 'Referral added', description: `${res.data.name} is now available.` });
      setDialogOpen(false);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Could not add referral',
        description: errorDetail(err, 'Referral creation failed'),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={className}>
      <Label>{label}</Label>
      <div className="flex gap-2 mt-1">
        <Select
          value={value || NONE}
          onValueChange={(v) => onValueChange?.(v === NONE ? '' : v)}
          disabled={loading}
        >
          <SelectTrigger className="flex-1">
            <SelectValue placeholder={loading ? 'Loading…' : 'Select referral'} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>Self / None</SelectItem>
            {referrals.length === 0 && !loading && (
              <SelectItem value="_empty" disabled>No referrals yet — add one →</SelectItem>
            )}
            {referrals.map((r) => (
              <SelectItem key={r.id} value={r.name}>
                {r.name}{r.village ? ` — ${r.village}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="icon" onClick={openCreate} title="Add referral">
          <UserPlus className="h-4 w-4" />
        </Button>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md" formNav="grid">
          <DialogHeader>
            <DialogTitle>Add Referral</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <div>
              <Label htmlFor="ref-name">Name *</Label>
              <Input
                id="ref-name"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="Doctor / clinic / agent name"
                required
              />
            </div>
            <div>
              <Label htmlFor="ref-phone">Phone</Label>
              <Input
                id="ref-phone"
                value={form.phone}
                onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
                placeholder="Optional"
              />
            </div>
            <div>
              <Label htmlFor="ref-village">Village / area</Label>
              <Input
                id="ref-village"
                value={form.village}
                onChange={(e) => setForm((p) => ({ ...p, village: e.target.value }))}
                placeholder="Optional"
              />
            </div>
            <div>
              <Label htmlFor="ref-mandal">Mandal</Label>
              <Input
                id="ref-mandal"
                value={form.mandal}
                onChange={(e) => setForm((p) => ({ ...p, mandal: e.target.value }))}
                placeholder="Optional"
              />
            </div>
            <div>
              <Label htmlFor="ref-district">District</Label>
              <Input
                id="ref-district"
                value={form.district}
                onChange={(e) => setForm((p) => ({ ...p, district: e.target.value }))}
                placeholder="Optional"
              />
            </div>
            <div className="flex gap-2 pt-1">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" className="flex-1" disabled={saving}>
                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Add & select'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
