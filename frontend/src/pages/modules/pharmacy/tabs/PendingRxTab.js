import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { RefreshCw, Pill, XCircle, Pencil, Plus, Trash2 } from 'lucide-react';
import { Textarea } from '../../../../components/ui/textarea';
import { Label } from '../../../../components/ui/label';
import { errMsg } from '../../PharmacyModule';
import { displayPharmacyNumericInput, pharmacyNoSpinInputClass } from '../../../../utils/pharmacyUnits';
import { MEDICINE_QTY_HINT, patchMedicineLine } from '../../../../utils/prescriptionSchedule';
import PharmacyMedicinePicker from '../../../../components/pharmacy/PharmacyMedicinePicker';

const blankEditRow = () => ({
  key: `new-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  item_id: null,
  medicine_id: '',
  medicine: null,
  quantity_prescribed: '1',
  quantity_dispensed: 0,
  dosage: '',
  duration: '',
  instructions: '',
});

function rowsFromRx(rx) {
  return (rx?.items || []).map((it) => ({
    key: `item-${it.item_id}`,
    item_id: it.item_id,
    medicine_id: it.medicine_id,
    medicine: {
      id: it.medicine_id,
      name: it.medicine_name || `Medicine #${it.medicine_id}`,
      medicine_code: it.is_unmapped ? 'UNMAPPED' : '',
    },
    quantity_prescribed: String(it.quantity_prescribed ?? ''),
    quantity_dispensed: Number(it.quantity_dispensed || 0),
    dosage: it.dosage || '',
    duration: it.duration || '',
    instructions: it.instructions || '',
  }));
}

export default function PendingRxTab() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [editRows, setEditRows] = useState([]);
  const [editNotes, setEditNotes] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/prescriptions/pending');
      setRows(r.data || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openDispense = (rx) => {
    const pending = (rx.items || []).filter((it) => Number(it.quantity_remaining || 0) > 0);
    if (pending.length === 0) {
      toast({ variant: 'destructive', title: 'Nothing left to dispense on this prescription' });
      return;
    }
    navigate('/dashboard/pharmacy/sales-counter', { state: { dispenseRx: rx } });
  };

  const openEdit = (rx) => {
    setEditTarget(rx);
    setEditRows(rowsFromRx(rx));
    setEditNotes(rx.notes || '');
    setEditOpen(true);
  };

  const updateEditRow = (key, patch) => {
    setEditRows((prev) => prev.map((row) => {
      if (row.key !== key) return row;
      const driver = ['dosage', 'duration'].find((field) => (
        Object.prototype.hasOwnProperty.call(patch, field) && Object.keys(patch).length === 1
      ));
      if (!driver) return { ...row, ...patch };
      let next = patchMedicineLine(row, driver, patch[driver]);
      const floor = Number(row.quantity_dispensed || 0);
      if (floor > 0 && Number(next.quantity_prescribed) < floor) {
        next = { ...next, quantity_prescribed: String(floor) };
      }
      return next;
    }));
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    if (editRows.length === 0) {
      toast({ variant: 'destructive', title: 'Add at least one medicine' });
      return;
    }
    for (const row of editRows) {
      if (!row.medicine_id) {
        toast({ variant: 'destructive', title: 'Select a medicine for every row' });
        return;
      }
      const qty = parseFloat(row.quantity_prescribed);
      if (!(qty > 0)) {
        toast({ variant: 'destructive', title: 'Quantity must be greater than 0' });
        return;
      }
      if (row.quantity_dispensed > 0 && qty < row.quantity_dispensed) {
        toast({
          variant: 'destructive',
          title: 'Quantity too low',
          description: `${row.medicine?.name || 'A line'} already dispensed ${row.quantity_dispensed}`,
        });
        return;
      }
    }
    setSavingEdit(true);
    try {
      const payload = {
        notes: editNotes,
        items: editRows.map((row) => ({
          item_id: row.item_id || undefined,
          medicine_id: Number(row.medicine_id),
          quantity_prescribed: parseFloat(row.quantity_prescribed),
          dosage: row.dosage || null,
          duration: row.duration || null,
          instructions: row.instructions || null,
        })),
      };
      await axios.put(`/api/pharmacy/prescriptions/${editTarget.id}/items`, payload);
      toast({ title: 'Prescription updated' });
      setEditOpen(false);
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Update failed', description: errMsg(e) });
    } finally {
      setSavingEdit(false);
    }
  };

  const openCancel = (rx) => {
    setCancelTarget(rx);
    setCancelReason('');
    setCancelOpen(true);
  };

  const submitCancel = async () => {
    const reason = cancelReason.trim();
    if (reason.length < 2) {
      toast({ variant: 'destructive', title: 'Enter a cancellation reason' });
      return;
    }
    setCancelling(true);
    try {
      const r = await axios.post(
        `/api/pharmacy/prescriptions/${cancelTarget.id}/cancel`,
        { reason },
      );
      const d = r.data || {};
      const detailBits = [];
      if (d.stock_ledger_rows_written) detailBits.push(`stock restored on ${d.stock_ledger_rows_written} batch(es)`);
      if (d.bill_items_removed) detailBits.push(`${d.bill_items_removed} bill line(s) removed`);
      if (d.credit_note_number) detailBits.push(`credit note ${d.credit_note_number} issued`);
      toast({
        title: 'Prescription cancelled',
        description: detailBits.length ? detailBits.join(' · ') : undefined,
      });
      setCancelOpen(false);
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Cancel failed', description: errMsg(e) });
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>Pending Prescriptions ({rows.length})</span>
          <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No pending prescriptions</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Rx #</th><th className="py-2 pr-4">Patient</th><th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Items</th><th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(rx => (
                  <tr key={rx.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{rx.prescription_number}</td>
                    <td className="py-2 pr-4 text-xs">
                      {rx.patient_name || '—'}
                      {rx.admission_number ? (
                        <span className="ml-1 font-mono text-[10px] text-gray-500">{rx.admission_number}</span>
                      ) : rx.admission_id ? <Badge variant="outline" className="ml-1 text-[10px]">IP</Badge> : null}
                    </td>
                    <td className="py-2 pr-4 text-xs">{new Date(rx.prescription_date).toLocaleString()}</td>
                    <td className="py-2 pr-4">{rx.items.length}</td>
                    <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{rx.status}</Badge></td>
                    <td className="py-2 text-right space-x-2 whitespace-nowrap">
                      <Button size="sm" variant="outline" onClick={() => openEdit(rx)}>
                        <Pencil className="h-3 w-3 mr-1" /> Edit
                      </Button>
                      <Button size="sm" onClick={() => openDispense(rx)}>
                        <Pill className="h-3 w-3 mr-1" /> Dispense
                      </Button>
                      <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => openCancel(rx)}>
                        <XCircle className="h-3 w-3 mr-1" /> Cancel
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-3xl w-[96vw] max-h-[90vh] flex flex-col overflow-hidden gap-0 p-0">
          <div className="shrink-0 border-b px-6 pt-5 pb-3">
            <DialogHeader className="space-y-1">
              <DialogTitle>Edit medicines — {editTarget?.prescription_number}</DialogTitle>
            </DialogHeader>
            <p className="text-xs text-gray-500 mt-2">
              Change, add, or remove medicines before dispensing. Lines already dispensed stay locked to that medicine.
            </p>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-3 space-y-3">
            <div>
              <Label className="text-xs">Notes</Label>
              <Textarea
                rows={2}
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                placeholder="Optional pharmacy / Rx notes"
              />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-xs">Medicines</Label>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEditRows((prev) => [...prev, blankEditRow()])}
              >
                <Plus className="h-3 w-3 mr-1" /> Add medicine
              </Button>
            </div>
            {editRows.map((row) => {
              const locked = row.quantity_dispensed > 0;
              return (
                <div key={row.key} className="border rounded-md p-3 space-y-2 bg-gray-50">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      {locked ? (
                        <div className="rounded border bg-white px-2 py-1.5 min-h-8">
                          <div className="font-medium text-sm truncate">{row.medicine?.name}</div>
                          <div className="text-[10px] text-amber-700">
                            Locked — {row.quantity_dispensed} already dispensed
                          </div>
                        </div>
                      ) : (
                        <PharmacyMedicinePicker
                          value={row.medicine_id || null}
                          medicine={row.medicine}
                          onSelect={(m) => updateEditRow(row.key, {
                            medicine_id: m.id,
                            medicine: m,
                          })}
                          placeholder="Search pharmacy catalog…"
                        />
                      )}
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-9 w-9 p-0 shrink-0"
                      disabled={locked || editRows.length === 1}
                      title={locked ? 'Cannot remove a partially dispensed line' : 'Remove'}
                      onClick={() => setEditRows((prev) => prev.filter((r) => r.key !== row.key))}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div>
                      <Label className="text-[10px] text-gray-500">Dosage</Label>
                      <Input
                        className="h-8"
                        placeholder="0.5 tab BD"
                        value={row.dosage}
                        onChange={(e) => updateEditRow(row.key, { dosage: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Duration</Label>
                      <Input
                        className="h-8"
                        placeholder="5 days"
                        value={row.duration}
                        onChange={(e) => updateEditRow(row.key, { duration: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Qty prescribed</Label>
                      <Input
                        className={`h-8 ${pharmacyNoSpinInputClass}`}
                        type="number"
                        min={locked ? row.quantity_dispensed : 0.01}
                        step="any"
                        title={MEDICINE_QTY_HINT}
                        value={displayPharmacyNumericInput(row.quantity_prescribed)}
                        onChange={(e) => updateEditRow(row.key, { quantity_prescribed: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Instructions</Label>
                      <Input
                        className="h-8"
                        placeholder="After food…"
                        value={row.instructions}
                        onChange={(e) => updateEditRow(row.key, { instructions: e.target.value })}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="shrink-0 border-t px-6 py-3 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <Button variant="outline" onClick={() => setEditOpen(false)} disabled={savingEdit}>
              Cancel
            </Button>
            <Button onClick={submitEdit} disabled={savingEdit}>
              {savingEdit ? 'Saving…' : 'Save changes'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel Rx — {cancelTarget?.prescription_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-gray-600">
              Any dispensed stock for this Rx will be returned to the original batch(es).
              If the prescription is already on an inpatient bill, the bill will either be
              adjusted in place (if still a draft) or offset by a credit-note (if locked / paid).
            </p>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Reason</label>
              <Textarea
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Patient discharged early / Prescribed in error"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)} disabled={cancelling}>
              Keep Rx
            </Button>
            <Button variant="destructive" onClick={submitCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : 'Cancel Rx'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
