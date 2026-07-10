import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2 } from 'lucide-react';
import { errMsg } from '../PharmacyModule';
import PharmacyStoreSelector from '../../../components/pharmacy/PharmacyStoreSelector';
import { usePharmacyStore } from '../../../contexts/PharmacyStoreContext';
import { displayPharmacyNumericInput, pharmacyNoSpinInputClass } from '../../../utils/pharmacyUnits';
import FormNavContainer from '../../../components/FormNavContainer';
import { navCellProps } from '../../../utils/formNavigation';
import { localDateString } from '../../../utils/localDate';

const TODAY = localDateString();

export default function TransferEntry() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = location.state || {};
  const { stores, activeStoreId } = usePharmacyStore();
  const masterStore = stores.find((s) => s.store_type === 'master');
  const satellites = stores.filter((s) => s.store_type === 'satellite' && s.is_active);

  const [header, setHeader] = useState({
    entry_date: TODAY,
    from_store_id: null,
    to_store_id: null,
    notes: '',
  });
  const [items, setItems] = useState([]);
  const [batches, setBatches] = useState([]);
  const [draftId, setDraftId] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (masterStore) {
      setHeader((h) => ({ ...h, from_store_id: masterStore.id }));
    }
  }, [masterStore?.id]);

  useEffect(() => {
    if (prefill.toStoreId) {
      setHeader((h) => ({ ...h, to_store_id: prefill.toStoreId }));
    }
  }, [prefill.toStoreId]);

  useEffect(() => {
    if (!header.from_store_id || !prefill.medicineId || batches.length === 0) return;
    const match = batches.find(
      (b) => b.medicine_id === prefill.medicineId && b.quantity_in_stock > 0,
    );
    if (match && items.length === 0) {
      setItems([{
        source_batch_id: match.id,
        quantity: prefill.qty || 1,
      }]);
    }
  }, [batches, prefill.medicineId, prefill.qty, header.from_store_id, items.length]);

  useEffect(() => {
    if (!header.from_store_id) return;
    axios.get('/api/pharmacy/inventory/batches', {
      params: { store_id: header.from_store_id, active_only: true, limit: 500 },
    }).then((r) => setBatches(r.data || [])).catch(() => setBatches([]));
  }, [header.from_store_id]);

  const addLine = () => setItems((s) => [...s, { source_batch_id: null, quantity: 1 }]);

  const buildPayload = () => ({
    entry_date: header.entry_date,
    from_store_id: header.from_store_id,
    to_store_id: header.to_store_id,
    notes: header.notes || null,
    items: items.filter((i) => i.source_batch_id && i.quantity > 0).map((i) => ({
      source_batch_id: i.source_batch_id,
      quantity: parseFloat(i.quantity),
    })),
  });

  const saveDraft = async () => {
    if (!header.to_store_id) {
      toast({ variant: 'destructive', title: 'Select destination store' });
      return;
    }
    setSubmitting(true);
    try {
      const payload = buildPayload();
      if (payload.items.length === 0) {
        toast({ variant: 'destructive', title: 'Add at least one line' });
        return;
      }
      const r = draftId
        ? await axios.put(`/api/pharmacy/transfers/${draftId}`, payload)
        : await axios.post('/api/pharmacy/transfers', payload);
      setDraftId(r.data.id);
      toast({ title: 'Transfer draft saved' });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const confirmTransfer = async () => {
    setSubmitting(true);
    try {
      let id = draftId;
      if (!id) {
        const r = await axios.post('/api/pharmacy/transfers', buildPayload());
        id = r.data.id;
        setDraftId(id);
      } else {
        await axios.put(`/api/pharmacy/transfers/${id}`, buildPayload());
      }
      await axios.post(`/api/pharmacy/transfers/${id}/confirm`);
      toast({ title: 'Transfer confirmed' });
      if (prefill.returnPath) {
        navigate(prefill.returnPath);
      } else {
        navigate('/dashboard/pharmacy/transfers');
      }
    } catch (e) {
      toast({ variant: 'destructive', title: 'Confirm failed', description: errMsg(e) });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4 max-w-5xl mx-auto p-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Button variant="ghost" onClick={() => navigate('/dashboard/pharmacy/transfers')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <PharmacyStoreSelector compact />
      </div>
      <h1 className="text-2xl font-bold">Stock Transfer</h1>
      <p className="text-gray-600">Move stock from master pharmacy to a satellite store.</p>
      {prefill.medicineName && (
        <p className="text-sm text-blue-700">
          Pre-filled for POS: {prefill.medicineName} (qty {prefill.qty || 1})
        </p>
      )}

      <FormNavContainer mode="grid" className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Transfer details</CardTitle></CardHeader>
        <CardContent className="grid md:grid-cols-2 gap-4">
          <div>
            <Label>Date</Label>
            <Input type="date" value={header.entry_date}
              onChange={(e) => setHeader({ ...header, entry_date: e.target.value })} />
          </div>
          <div>
            <Label>From (master)</Label>
            <Input value={masterStore ? `${masterStore.code} — ${masterStore.name}` : '—'} disabled />
          </div>
          <div>
            <Label>To store</Label>
            <Select
              value={header.to_store_id ? String(header.to_store_id) : undefined}
              onValueChange={(v) => setHeader({ ...header, to_store_id: parseInt(v, 10) })}
            >
              <SelectTrigger><SelectValue placeholder="Select satellite store" /></SelectTrigger>
              <SelectContent>
                {satellites.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>{s.code} — {s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Label>Notes</Label>
            <Textarea value={header.notes} onChange={(e) => setHeader({ ...header, notes: e.target.value })} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row justify-between items-center">
          <CardTitle>Items</CardTitle>
          <Button size="sm" onClick={addLine}><Plus className="h-4 w-4 mr-1" /> Add line</Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.map((line, idx) => (
            <div key={idx} className="grid md:grid-cols-12 gap-2 items-end border-b pb-3">
              <div className="md:col-span-7">
                <Label>Batch</Label>
                <Select
                  value={line.source_batch_id ? String(line.source_batch_id) : undefined}
                  onValueChange={(v) => {
                    const next = [...items];
                    next[idx] = { ...next[idx], source_batch_id: parseInt(v, 10) };
                    setItems(next);
                  }}
                >
                  <SelectTrigger><SelectValue placeholder="Select batch" /></SelectTrigger>
                  <SelectContent>
                    {batches.filter((b) => b.quantity_in_stock > 0).map((b) => (
                      <SelectItem key={b.id} value={String(b.id)}>
                        {b.medicine_name} · {b.batch_number} · qty {b.quantity_in_stock}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="md:col-span-3">
                <Label>Qty</Label>
                <Input className={pharmacyNoSpinInputClass} type="number" min="0" step="1"
                  value={displayPharmacyNumericInput(line.quantity)}
                  onChange={(e) => {
                    const next = [...items];
                    next[idx] = { ...next[idx], quantity: e.target.value };
                    setItems(next);
                  }} />
              </div>
              <div className="md:col-span-2">
                <Button variant="ghost" size="sm" onClick={() => setItems(items.filter((_, i) => i !== idx))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex gap-2 justify-end">
        <Button variant="outline" onClick={saveDraft} disabled={submitting}>
          <Save className="h-4 w-4 mr-1" /> Save Draft
        </Button>
        <Button onClick={confirmTransfer} disabled={submitting}>
          <CheckCircle2 className="h-4 w-4 mr-1" /> Confirm Transfer
        </Button>
      </div>
      </FormNavContainer>
    </div>
  );
}
