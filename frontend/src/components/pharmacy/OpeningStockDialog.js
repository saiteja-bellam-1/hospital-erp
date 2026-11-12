import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { useToast } from '../../hooks/use-toast';
import PharmacyMedicinePicker from './PharmacyMedicinePicker';
import PharmacyMasterSelectWithCreate from './PharmacyMasterSelectWithCreate';
import { usePharmacyStore } from '../../contexts/PharmacyStoreContext';
import { pharmacyNoSpinInputClass } from '../../utils/pharmacyUnits';
import { errMsg } from '../../pages/modules/PharmacyModule';

const emptyForm = (supplierId = null) => ({
  medicine: null,
  batch_number: '',
  expiry_mm_yyyy: '',
  quantity: '',
  mrp: '',
  purchase_rate: '',
  rate_a: '',
  rate_b: '',
  strip_conversion_factor: '1',
  free_quantity: '',
  supplier_id: supplierId,
});

function formatExpiryInput(raw) {
  const digits = String(raw || '').replace(/\D/g, '').slice(0, 6);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}/${digits.slice(2)}`;
}

/** Last day of the typed month, as YYYY-MM-DD. Null when the text is not a month. */
function expiryToISO(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  let m = s.match(/^(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})$/);
  if (!m) {
    const digits = s.replace(/\D/g, '');
    if (digits.length === 4 || digits.length === 6) {
      m = ['', digits.slice(0, 2), digits.slice(2)];
    } else {
      return null;
    }
  }
  const mo = parseInt(m[1], 10);
  let yr = parseInt(m[2], 10);
  if (yr < 100) yr += 2000;
  if (mo < 1 || mo > 12) return null;
  const last = new Date(yr, mo, 0);
  const yyyy = last.getFullYear();
  const mm = String(last.getMonth() + 1).padStart(2, '0');
  const dd = String(last.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function expiryIsPast(iso) {
  if (!iso) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(`${iso}T12:00:00`) < today;
}

function moneyOrNull(v) {
  if (v === '' || v == null) return null;
  const n = parseFloat(v);
  if (!Number.isFinite(n)) return null;
  return Math.round(n * 100) / 100;
}

function formStarted(form) {
  return Boolean(
    form.medicine
    || String(form.batch_number || '').trim()
    || String(form.quantity || '').trim()
    || String(form.expiry_mm_yyyy || '').trim(),
  );
}

function validateLine(form, existingLines) {
  if (!form.medicine?.id) return 'Pick a medicine from the catalog.';
  const batch = String(form.batch_number || '').trim();
  if (!batch) return 'Batch number is required.';
  const expiry = expiryToISO(form.expiry_mm_yyyy);
  if (!expiry) return 'Enter expiry as MM/YYYY.';
  const qty = Number(form.quantity);
  if (!Number.isInteger(qty) || qty <= 0) return 'Quantity must be a whole number of tabs greater than 0.';
  const scf = parseInt(form.strip_conversion_factor, 10);
  if (!Number.isInteger(scf) || scf < 1) return 'Tabs/strip must be a whole number of at least 1.';
  const freeRaw = String(form.free_quantity || '').trim();
  if (freeRaw) {
    const free = Number(freeRaw);
    if (!Number.isInteger(free) || free < 0) return 'Free quantity must be a whole number.';
  }
  const dup = existingLines.some((ln) => (
    ln.medicine?.id === form.medicine.id
    && String(ln.batch_number || '').trim().toLowerCase() === batch.toLowerCase()
  ));
  if (dup) return `Batch ${batch} is already in this list for ${form.medicine.name}.`;
  return null;
}

function toPayload(form, notes) {
  const freeRaw = String(form.free_quantity || '').trim();
  return {
    medicine_id: form.medicine.id,
    batch_number: String(form.batch_number || '').trim(),
    expiry_date: expiryToISO(form.expiry_mm_yyyy),
    quantity: parseInt(form.quantity, 10),
    mrp: moneyOrNull(form.mrp),
    purchase_rate: moneyOrNull(form.purchase_rate),
    rate_a: moneyOrNull(form.rate_a),
    rate_b: moneyOrNull(form.rate_b),
    strip_conversion_factor: Math.max(1, parseInt(form.strip_conversion_factor, 10) || 1),
    free_quantity: freeRaw ? parseInt(freeRaw, 10) : 0,
    supplier_id: form.supplier_id || null,
    hsn_id: form.medicine.hsn_id || null,
    notes: String(notes || '').trim() || null,
  };
}

function applyMedicine(form, medicine) {
  if (!medicine) {
    return { ...emptyForm(form.supplier_id) };
  }
  const rateA = medicine.rate_a || medicine.mrp;
  return {
    ...form,
    medicine,
    mrp: medicine.mrp ? String(medicine.mrp) : '',
    purchase_rate: medicine.purchase_rate ? String(medicine.purchase_rate) : '',
    rate_a: rateA ? String(rateA) : '',
    rate_b: medicine.rate_b ? String(medicine.rate_b) : '',
    strip_conversion_factor: String(Math.max(1, parseInt(medicine.strip_conversion_factor, 10) || 1)),
  };
}

export default function OpeningStockDialog({ open, onOpenChange, onSaved }) {
  const { toast } = useToast();
  const { activeStore, activeStoreId } = usePharmacyStore();
  const [form, setForm] = useState(() => emptyForm());
  const [lines, setLines] = useState([]);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(emptyForm());
    setLines([]);
    setNotes('');
    setSaving(false);
  }, [open]);

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const addLine = () => {
    const message = validateLine(form, lines);
    if (message) {
      toast({ variant: 'destructive', title: message });
      return;
    }
    setLines((prev) => [...prev, form]);
    setForm(emptyForm(form.supplier_id));
  };

  const editLine = (index) => {
    const row = lines[index];
    if (!row) return;
    setForm(row);
    setLines((prev) => prev.filter((_, i) => i !== index));
  };

  const save = async () => {
    let pending = lines;
    if (formStarted(form)) {
      const message = validateLine(form, lines);
      if (message) {
        toast({ variant: 'destructive', title: message });
        return;
      }
      pending = [...lines, form];
    }
    if (!pending.length) {
      toast({ variant: 'destructive', title: 'Add at least one batch' });
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/api/pharmacy/opening-stock', {
        store_id: activeStoreId || null,
        lines: pending.map((ln) => toPayload(ln, notes)),
      });
      const n = res.data?.created || pending.length;
      toast({
        title: 'Opening stock saved',
        description: n === 1 ? '1 batch added' : `${n} batches added`,
      });
      onOpenChange(false);
      onSaved?.();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const description = typeof detail === 'string'
        ? detail
        : (Array.isArray(detail) && detail[0]?.msg) || errMsg(e);
      toast({ variant: 'destructive', title: 'Could not save opening stock', description });
    } finally {
      setSaving(false);
    }
  };

  const expiryIso = expiryToISO(form.expiry_mm_yyyy);
  const scf = Math.max(1, parseInt(form.strip_conversion_factor, 10) || 1);
  const qtyNum = parseInt(form.quantity, 10);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Enter opening stock</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-gray-500 -mt-2">
          Adds a new batch for a medicine already in the catalog. Quantity is in tabs.
          {activeStore?.name ? ` Stock goes to ${activeStore.name}.` : ''}
          {' '}If the batch already exists, use Adjust instead.
        </p>

        <div className="space-y-3">
          <div>
            <Label className="text-xs">Medicine</Label>
            <PharmacyMedicinePicker
              value={form.medicine?.id || null}
              medicine={form.medicine}
              onSelect={(m) => setForm((prev) => applyMedicine(prev, m))}
              placeholder="Search name or code…"
              wideMenu
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <Label className="text-xs">Batch</Label>
              <Input
                className="h-8"
                value={form.batch_number}
                onChange={(e) => setField('batch_number', e.target.value)}
                placeholder="BATCH001"
              />
            </div>
            <div>
              <Label className="text-xs">Expiry (MM/YYYY)</Label>
              <Input
                className="h-8"
                inputMode="numeric"
                placeholder="06/2027"
                value={form.expiry_mm_yyyy}
                onChange={(e) => setField('expiry_mm_yyyy', formatExpiryInput(e.target.value))}
              />
              {expiryIso && expiryIsPast(expiryIso) ? (
                <p className="text-[10px] text-amber-700 mt-0.5">This batch is already expired.</p>
              ) : null}
            </div>
            <div>
              <Label className="text-xs">Quantity (tabs)</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={1}
                step={1}
                value={form.quantity}
                onChange={(e) => setField('quantity', e.target.value)}
              />
              {scf > 1 && Number.isInteger(qtyNum) && qtyNum > 0 ? (
                <p className="text-[10px] text-gray-500 mt-0.5">
                  ≈ {(qtyNum / scf).toLocaleString(undefined, { maximumFractionDigits: 2 })} strips
                </p>
              ) : null}
            </div>
            <div>
              <Label className="text-xs">Tabs / strip</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={1}
                step={1}
                value={form.strip_conversion_factor}
                onChange={(e) => setField('strip_conversion_factor', e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <Label className="text-xs">MRP</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={0}
                step="any"
                value={form.mrp}
                onChange={(e) => setField('mrp', e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">P-Rate</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={0}
                step="any"
                value={form.purchase_rate}
                onChange={(e) => setField('purchase_rate', e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">Rate A</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={0}
                step="any"
                value={form.rate_a}
                onChange={(e) => setField('rate_a', e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">Rate B</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={0}
                step="any"
                value={form.rate_b}
                onChange={(e) => setField('rate_b', e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Free qty (tabs)</Label>
              <Input
                className={`h-8 ${pharmacyNoSpinInputClass}`}
                type="number"
                min={0}
                step={1}
                value={form.free_quantity}
                onChange={(e) => setField('free_quantity', e.target.value)}
              />
              <p className="text-[10px] text-gray-500 mt-0.5">Recorded on the batch. Not added on top of quantity.</p>
            </div>
            <div>
              <Label className="text-xs">Supplier</Label>
              <PharmacyMasterSelectWithCreate
                path="suppliers"
                value={form.supplier_id}
                onChange={(id) => setField('supplier_id', id)}
                placeholder="Optional"
                allowEmpty
                compact
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button type="button" size="sm" variant="outline" onClick={addLine}>
              <Plus className="h-3 w-3 mr-1" /> Add batch
            </Button>
          </div>

          {lines.length > 0 && (
            <div className="border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-1.5 px-2">Medicine</th>
                    <th className="py-1.5 px-2">Batch</th>
                    <th className="py-1.5 px-2">Expiry</th>
                    <th className="py-1.5 px-2">Qty</th>
                    <th className="py-1.5 px-2">MRP</th>
                    <th className="py-1.5 px-2 w-16" />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((ln, i) => (
                    <tr key={`${ln.medicine?.id}-${ln.batch_number}-${i}`} className="border-b">
                      <td className="py-1.5 px-2">
                        <button type="button" className="text-left hover:underline" onClick={() => editLine(i)}>
                          {ln.medicine?.name}
                        </button>
                        <div className="text-[10px] text-gray-500 font-mono">{ln.medicine?.medicine_code}</div>
                      </td>
                      <td className="py-1.5 px-2 font-mono text-xs">{ln.batch_number}</td>
                      <td className="py-1.5 px-2 text-xs">{ln.expiry_mm_yyyy}</td>
                      <td className="py-1.5 px-2 tabular-nums">{ln.quantity}</td>
                      <td className="py-1.5 px-2 tabular-nums">{ln.mrp || '—'}</td>
                      <td className="py-1.5 px-2 text-right">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          title="Remove"
                          onClick={() => setLines((prev) => prev.filter((_, idx) => idx !== i))}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div>
            <Label className="text-xs">Notes</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Opening stock"
              rows={2}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
            Save opening stock
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
