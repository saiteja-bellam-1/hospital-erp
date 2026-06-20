import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Loader2 } from 'lucide-react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { errorDetail } from '../../utils/apiErrors';
import { PHARMACY_MASTER_FIELDS, blankFromFields } from './pharmacyMasterFields';

const NONE = '__none';

/**
 * Pharmacy master dropdown with a + button to quick-create a missing option.
 *
 * @param {string} path - API segment under /api/pharmacy/ (e.g. "categories")
 * @param {number|null} value - Selected row id
 * @param {(id: number|null) => void} onChange
 * @param {object[]} [options] - Controlled list; fetched when omitted
 * @param {(list: object[]) => void} [onOptionsChange]
 */
export default function PharmacyMasterSelectWithCreate({
  path,
  value,
  onChange,
  options: controlledOptions,
  onOptionsChange,
  createFields,
  createTitle,
  placeholder = 'Select…',
  allowEmpty = false,
  labelKey = 'name',
  format,
  label,
  className = '',
  compact = false,
  activeOnly = true,
}) {
  const spec = PHARMACY_MASTER_FIELDS[path] || {};
  const fields = createFields ?? spec.fields ?? [{ key: 'name', label: 'Name', required: true }];
  const dialogTitle = createTitle ?? spec.createTitle ?? 'Add';

  const { toast } = useToast();
  const [internalOptions, setInternalOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(() => blankFromFields(fields));

  const options = controlledOptions ?? internalOptions;
  const setOptions = (list) => {
    if (controlledOptions == null) setInternalOptions(list);
    onOptionsChange?.(list);
  };

  useEffect(() => {
    if (controlledOptions != null) return undefined;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await axios.get(`/api/pharmacy/${path}`, {
          params: { active_only: activeOnly },
        });
        if (!cancelled) setInternalOptions(res.data || []);
      } catch {
        if (!cancelled) setInternalOptions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [path, controlledOptions, activeOnly]);

  const openCreate = () => {
    setForm(blankFromFields(fields));
    setDialogOpen(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    for (const f of fields) {
      if (f.required && !String(form[f.key] ?? '').trim()) {
        toast({ variant: 'destructive', title: `${f.label} is required` });
        return;
      }
    }
    const payload = { is_active: true };
    fields.forEach((f) => {
      const raw = form[f.key];
      if (f.type === 'number') {
        payload[f.key] = raw === '' || raw == null ? (f.default ?? 0) : parseFloat(raw);
      } else {
        const s = String(raw ?? '').trim();
        payload[f.key] = s || null;
      }
    });
    setSaving(true);
    try {
      const res = await axios.post(`/api/pharmacy/${path}`, payload);
      const next = [...options, res.data].sort((a, b) => {
        const av = (format ? format(a) : a[labelKey]) || '';
        const bv = (format ? format(b) : b[labelKey]) || '';
        return String(av).localeCompare(String(bv));
      });
      setOptions(next);
      onChange?.(res.data.id);
      toast({ title: 'Created', description: `${dialogTitle.replace(/^Add /, '')} added.` });
      setDialogOpen(false);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Create failed',
        description: errorDetail(err, 'Could not save'),
      });
    } finally {
      setSaving(false);
    }
  };

  const triggerClass = compact ? 'h-8 flex-1 min-w-0' : 'flex-1';

  const selectControl = (
    <Select
      value={value == null ? (allowEmpty ? NONE : '') : String(value)}
      onValueChange={(v) => onChange?.(v === NONE ? null : Number(v))}
      disabled={loading}
    >
      <SelectTrigger className={triggerClass}>
        <SelectValue placeholder={loading ? 'Loading…' : placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowEmpty && <SelectItem value={NONE}>(none)</SelectItem>}
        {options.length === 0 && !loading && (
          <SelectItem value="_empty" disabled>No options — add one →</SelectItem>
        )}
        {options.map((o) => (
          <SelectItem key={o.id} value={String(o.id)}>
            {format ? format(o) : o[labelKey]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const addButton = (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={compact ? 'h-8 w-8 shrink-0' : undefined}
      onClick={openCreate}
      title={dialogTitle}
    >
      <Plus className="h-4 w-4" />
    </Button>
  );

  return (
    <div className={className}>
      {label && <Label className="text-xs">{label}</Label>}
      <div className={`flex gap-2 ${label ? 'mt-1' : ''}`}>
        {selectControl}
        {addButton}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            {fields.map((f) => (
              <div key={f.key}>
                <Label htmlFor={`pharm-master-${path}-${f.key}`}>
                  {f.label}{f.required ? ' *' : ''}
                </Label>
                {f.type === 'textarea' ? (
                  <Textarea
                    id={`pharm-master-${path}-${f.key}`}
                    rows={2}
                    value={form[f.key] || ''}
                    onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                  />
                ) : (
                  <Input
                    id={`pharm-master-${path}-${f.key}`}
                    type={f.type === 'number' ? 'number' : 'text'}
                    step={f.type === 'number' ? '0.01' : undefined}
                    value={form[f.key] ?? ''}
                    onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                  />
                )}
              </div>
            ))}
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Add & select'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
