import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Save, Settings2 } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';

const RATE_OPTIONS = [
  { value: 'A', label: 'Rate A' },
  { value: 'B', label: 'Rate B' },
];

export default function SetupTab() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    use_default_rate_tiers: false,
    default_rate_tier_cash: 'A',
    default_rate_tier_credit: 'A',
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get('/api/pharmacy/pos-settings');
        const d = r.data || {};
        if (!cancelled) {
          setForm({
            use_default_rate_tiers: !!d.use_default_rate_tiers,
            default_rate_tier_cash: d.default_rate_tier_cash === 'B' ? 'B' : 'A',
            default_rate_tier_credit: d.default_rate_tier_credit === 'B' ? 'B' : 'A',
          });
        }
      } catch (e) {
        if (!cancelled) {
          toast({ variant: 'destructive', title: 'Failed to load settings', description: errMsg(e) });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [toast]);

  const setField = (key, value) => setForm((s) => ({ ...s, [key]: value }));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.put('/api/pharmacy/pos-settings', form);
      toast({
        title: 'Saved',
        description: form.use_default_rate_tiers
          ? 'Default rates enabled — POS will skip the rate picker'
          : 'Default rates disabled — POS will ask for Rate A/B per line',
      });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(err) });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500 py-8 text-center">Loading settings…</p>;
  }

  return (
    <form onSubmit={handleSave} className="space-y-4 max-w-2xl">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            POS Default Rate Tiers
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-start gap-3 rounded-md border px-3 py-3 cursor-pointer hover:bg-gray-50">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 rounded border-gray-300"
              checked={form.use_default_rate_tiers}
              onChange={(e) => setField('use_default_rate_tiers', e.target.checked)}
            />
            <span>
              <span className="block text-sm font-medium text-gray-900">Use default rates on POS</span>
              <span className="block text-xs text-gray-500 mt-0.5">
                When enabled, cash/credit defaults are applied automatically and the Rate A/B popup is skipped.
                When disabled, staff pick Rate A or B after choosing a batch.
              </span>
            </span>
          </label>

          <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 ${form.use_default_rate_tiers ? '' : 'opacity-50'}`}>
            <div className="space-y-1.5">
              <Label>Cash bills</Label>
              <Select
                value={form.default_rate_tier_cash}
                onValueChange={(v) => setField('default_rate_tier_cash', v)}
                disabled={!form.use_default_rate_tiers}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RATE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Credit bills</Label>
              <Select
                value={form.default_rate_tier_credit}
                onValueChange={(v) => setField('default_rate_tier_credit', v)}
                disabled={!form.use_default_rate_tiers}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RATE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button type="submit" disabled={saving}>
            <Save className="h-4 w-4 mr-2" />
            {saving ? 'Saving…' : 'Save settings'}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
