import React, { useState } from 'react';
import { Button } from '../ui/button';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '../ui/dialog';
import { Edit2, Pill, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import {
  BLANK_TAKE_HOME_MED,
  foodTimingLabel,
  frequencyScheduleLabel,
} from '../../utils/prescriptionSchedule';
import TakeHomeMedicineForm from './TakeHomeMedicineForm';

function medSummaryLine(med) {
  const parts = [
    med.dosage?.trim(),
    frequencyScheduleLabel(med.frequency_schedule),
    foodTimingLabel(med.food_timing),
    med.duration?.trim() && `${med.duration.trim()}`,
    med.quantity && `Qty ${med.quantity}`,
  ].filter(Boolean);
  return parts.join(' · ');
}

/**
 * Take-home medicine list with add/edit in a dialog (discharge flows).
 */
export default function TakeHomeMedicinesSection({
  medications = [],
  onMedicationsChange,
  admissionId,
  title = 'Take-home medications',
  description,
}) {
  const { toast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editIndex, setEditIndex] = useState(null);
  const [draft, setDraft] = useState({ ...BLANK_TAKE_HOME_MED });

  const openAdd = () => {
    setEditIndex(null);
    setDraft({ ...BLANK_TAKE_HOME_MED });
    setDialogOpen(true);
  };

  const openEdit = (idx) => {
    setEditIndex(idx);
    setDraft({ ...medications[idx] });
    setDialogOpen(true);
  };

  const handleSave = (e) => {
    e.preventDefault();
    if (!(draft.medicine_name || '').trim()) {
      toast({ variant: 'destructive', title: 'Medicine required', description: 'Enter or select a medicine name.' });
      return;
    }
    const next = [...medications];
    if (editIndex === null) next.push({ ...draft });
    else next[editIndex] = { ...draft };
    onMedicationsChange(next);
    setDialogOpen(false);
  };

  const handleRemove = (idx) => {
    onMedicationsChange(medications.filter((_, i) => i !== idx));
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-sm text-gray-700 flex items-center gap-2">
          <Pill className="h-4 w-4" /> {title}
        </h3>
        <Button type="button" size="sm" variant="outline" onClick={openAdd}>
          <Plus className="h-3 w-3 mr-1" /> Add medicine
        </Button>
      </div>
      {description && (
        <p className="text-xs text-gray-500 mb-2">{description}</p>
      )}
      {medications.length === 0 ? (
        <p className="text-xs text-gray-500 italic border rounded p-3 bg-gray-50">
          No take-home medications yet. Click <b>Add medicine</b> to prescribe one.
        </p>
      ) : (
        <div className="border rounded-lg overflow-hidden divide-y bg-white">
          {medications.map((m, idx) => (
            <div key={idx} className="flex items-start gap-2 px-3 py-2.5 hover:bg-gray-50/80">
              <span className="text-xs text-gray-400 w-5 pt-0.5 shrink-0">{idx + 1}.</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">
                  {m.medicine_name}
                </div>
                {medSummaryLine(m) && (
                  <div className="text-xs text-gray-500 mt-0.5">{medSummaryLine(m)}</div>
                )}
                {m.instructions?.trim() && (
                  <div className="text-xs text-gray-400 mt-0.5 italic">{m.instructions.trim()}</div>
                )}
              </div>
              <div className="flex shrink-0 gap-0.5">
                <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0"
                        onClick={() => openEdit(idx)} title="Edit">
                  <Edit2 className="h-3.5 w-3.5 text-gray-500" />
                </Button>
                <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0"
                        onClick={() => handleRemove(idx)} title="Remove">
                  <Trash2 className="h-3.5 w-3.5 text-red-500" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editIndex === null ? 'Add medicine' : 'Edit medicine'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSave} className="space-y-4">
            <TakeHomeMedicineForm
              med={draft}
              onChange={setDraft}
              admissionId={admissionId}
            />
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit">
                {editIndex === null ? 'Add to list' : 'Save changes'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
