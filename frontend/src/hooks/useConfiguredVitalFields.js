import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

export const DEFAULT_VITAL_FIELDS = [
  'height',
  'weight',
  'blood_pressure',
  'heart_rate',
  'temperature',
  'respiratory_rate',
  'spo2',
];

export const EMPTY_VITALS_FORM = {
  blood_pressure_systolic: '',
  blood_pressure_diastolic: '',
  heart_rate: '',
  temperature: '',
  weight: '',
  height: '',
  respiratory_rate: '',
  oxygen_saturation: '',
  pain_scale: '',
  bmi: '',
  notes: '',
  recorded_date: '',
};

/**
 * Hospital-configured OPD vital fields (from Print Settings / guided setup).
 * Used by reception, nurse, and doctor vitals entry screens.
 */
export function useConfiguredVitalFields() {
  const query = useQuery({
    queryKey: ['hospital-vitals-config'],
    queryFn: async () => {
      const res = await axios.get('/api/hospital/vitals-config');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const vitalFields =
    Array.isArray(query.data?.vital_fields) && query.data.vital_fields.length
      ? query.data.vital_fields
      : DEFAULT_VITAL_FIELDS;

  return {
    vitalFields,
    vitalCatalog: query.data?.vital_catalog || [],
    isLoading: query.isLoading,
    refetch: query.refetch,
    isEnabled: (key) => vitalFields.includes(key),
  };
}

export function invalidateVitalsConfigCache(queryClient) {
  if (queryClient) {
    queryClient.invalidateQueries({ queryKey: ['hospital-vitals-config'] });
  }
}

/** Height/weight inputs are needed whenever those fields or BMI are selected. */
export function showHeightInput(fields) {
  return fields.includes('height') || fields.includes('bmi');
}

export function showWeightInput(fields) {
  return fields.includes('weight') || fields.includes('bmi');
}

export function showBmiOutput(fields) {
  return fields.includes('bmi') || (fields.includes('height') && fields.includes('weight'));
}

/**
 * Build vital_signs payload containing only configured fields (+ metadata).
 */
export function buildVitalSignsPayload(form, vitalFields, { recordedBy } = {}) {
  const enabled = new Set(vitalFields || DEFAULT_VITAL_FIELDS);
  const data = {};

  if (enabled.has('blood_pressure')) {
    const sys = (form.blood_pressure_systolic || '').toString().trim();
    const dia = (form.blood_pressure_diastolic || '').toString().trim();
    if (sys || dia) data.blood_pressure = `${sys}/${dia}`;
  }
  if (enabled.has('heart_rate') && form.heart_rate !== '' && form.heart_rate != null) {
    data.heart_rate = form.heart_rate;
  }
  if (enabled.has('temperature') && form.temperature !== '' && form.temperature != null) {
    data.temperature = form.temperature;
  }
  if ((enabled.has('weight') || enabled.has('bmi')) && form.weight !== '' && form.weight != null) {
    data.weight = form.weight;
  }
  if ((enabled.has('height') || enabled.has('bmi')) && form.height !== '' && form.height != null) {
    data.height = form.height;
  }
  if (enabled.has('respiratory_rate') && form.respiratory_rate !== '' && form.respiratory_rate != null) {
    data.respiratory_rate = form.respiratory_rate;
  }
  if (enabled.has('spo2') && form.oxygen_saturation !== '' && form.oxygen_saturation != null) {
    data.oxygen_saturation = form.oxygen_saturation;
  }
  if (enabled.has('pain_scale') && form.pain_scale !== '' && form.pain_scale != null) {
    data.pain_scale = form.pain_scale;
  }
  if (showBmiOutput([...enabled]) && form.bmi) {
    data.bmi = form.bmi;
  }
  if (form.recorded_date) data.recorded_date = form.recorded_date;
  if (recordedBy) data.recorded_by = recordedBy;

  return data;
}
