import React from 'react';
import FormNavContainer from '../FormNavContainer';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import MedicineLookupInput from '../inpatient/MedicineLookupInput';
import PrescriptionScheduleFields from './PrescriptionScheduleFields';

/** Single take-home medicine row — used inside the add/edit dialog. */
export default function TakeHomeMedicineForm({ med, onChange, admissionId }) {
  const set = (key, val) => onChange({ ...med, [key]: val });

  return (
    <FormNavContainer mode="grid" className="space-y-3">
      <div>
        <Label className="text-xs text-gray-500">Medicine *</Label>
        <MedicineLookupInput
          admissionId={admissionId}
          value={med.medicine_name}
          medicineId={med.medicine_id}
          placeholder="Search catalog or type free-text"
          onChange={({ medicine_id, medicine_name }) => {
            onChange({
              ...med,
              medicine_id: medicine_id || '',
              medicine_name,
            });
          }}
        />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div>
          <Label className="text-xs text-gray-500">Dosage</Label>
          <Input
            placeholder="500 mg"
            value={med.dosage}
            onChange={(e) => set('dosage', e.target.value)}
          />
        </div>
        <PrescriptionScheduleFields
          frequencySchedule={med.frequency_schedule}
          foodTiming={med.food_timing}
          onFrequencyChange={(v) => set('frequency_schedule', v)}
          onFoodTimingChange={(v) => set('food_timing', v)}
          labelClassName="text-xs text-gray-500"
          selectClassName="w-full h-9 text-xs border border-gray-200 rounded px-2 bg-white"
        />
        <div>
          <Label className="text-xs text-gray-500">Duration</Label>
          <Input
            placeholder="5 days"
            value={med.duration}
            onChange={(e) => set('duration', e.target.value)}
          />
        </div>
        <div>
          <Label className="text-xs text-gray-500">Quantity</Label>
          <Input
            type="number"
            min="1"
            placeholder="10"
            value={med.quantity}
            onChange={(e) => set('quantity', e.target.value)}
          />
        </div>
      </div>
      <div>
        <Label className="text-xs text-gray-500">Extra instructions (optional)</Label>
        <Input
          placeholder="With water, avoid alcohol, etc."
          value={med.instructions}
          onChange={(e) => set('instructions', e.target.value)}
        />
      </div>
    </FormNavContainer>
  );
}
