import {
  calcMedicineQuantity,
  parseDurationDays,
  patchMedicineLine,
} from './prescriptionSchedule';

describe('calcMedicineQuantity', () => {
  test('1 tablet, morning and night, for 5 days is 10', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab',
      frequencySchedule: '1-0-1',
      duration: '5 days',
    })).toBe(10);
  });

  test('2 tablets three times a day for 1 week is 42', () => {
    expect(calcMedicineQuantity({
      dosage: '2 tablets',
      frequencySchedule: '1-1-1',
      duration: '1 week',
    })).toBe(42);
  });

  test('half tablet at night for 10 days is 5', () => {
    expect(calcMedicineQuantity({
      dosage: '1/2 tab',
      frequencySchedule: '0-0-1',
      duration: '10 days',
    })).toBe(5);
  });

  test('every 8 hours is three doses a day', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab',
      frequencySchedule: 'q8h',
      duration: '5 days',
    })).toBe(15);
  });

  test('every 6 hours is four doses a day', () => {
    expect(calcMedicineQuantity({
      dosage: '0.5 tab',
      frequencySchedule: 'q6h',
      duration: '2 days',
    })).toBe(4);
  });

  test('decimal dosage is kept, not rounded up to a whole tablet', () => {
    expect(calcMedicineQuantity({
      dosage: '1.5 tab',
      frequencySchedule: '1-0-0',
      duration: '5 days',
    })).toBe(7.5);
    expect(calcMedicineQuantity({
      dosage: '0.5',
      frequencySchedule: '1-0-1',
      duration: '3 days',
    })).toBe(3);
    expect(calcMedicineQuantity({
      dosage: '.5 tab',
      frequencySchedule: '0-0-1',
      duration: '3 days',
    })).toBe(1.5);
  });

  test('strength-only dosage still counts one unit per dose', () => {
    expect(calcMedicineQuantity({
      dosage: '500 mg',
      frequencySchedule: '1-0-1',
      duration: '5',
    })).toBe(10);
  });

  test('a written 2-0-2 schedule is the daily total, not multiplied again', () => {
    expect(calcMedicineQuantity({
      dosage: '2-0-2',
      duration: '5 days',
    })).toBe(20);
  });

  test('BD in the dosage text is twice a day when no schedule is selected', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab BD',
      duration: '5 days',
    })).toBe(10);
  });

  test('a saved dosage line that names morning and night is twice a day', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab - morning, night after food',
      duration: '7 days',
    })).toBe(14);
  });

  test('10 ml three times a day for 3 days is 90', () => {
    expect(calcMedicineQuantity({
      dosage: '10 ml',
      frequencySchedule: '1-1-1',
      duration: '3 days',
    })).toBe(90);
  });

  test('one month is 30 days', () => {
    expect(parseDurationDays('2 months')).toBe(60);
    expect(calcMedicineQuantity({
      dosage: '1 cap',
      frequencySchedule: '1-0-0',
      duration: '1 month',
    })).toBe(30);
  });

  test('SOS is left for the user to enter', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab SOS',
      frequencySchedule: '1-0-1',
      duration: '5 days',
    })).toBeNull();
  });

  test('incomplete duration does not invent a quantity', () => {
    expect(calcMedicineQuantity({
      dosage: '1 tab',
      frequencySchedule: '1-0-1',
      duration: 'as directed',
    })).toBeNull();
  });

  test('editing dosage updates quantity and a manual quantity edit is kept', () => {
    const row = {
      dosage: '',
      frequency_schedule: '1-0-1',
      duration: '5 days',
      quantity_prescribed: 1,
    };
    const calculated = patchMedicineLine(row, 'dosage', '1 tab');
    expect(calculated.quantity_prescribed).toBe(10);
    const overridden = patchMedicineLine(calculated, 'quantity_prescribed', '4');
    expect(overridden.quantity_prescribed).toBe('4');
    expect(patchMedicineLine(overridden, 'duration', '7 days').quantity_prescribed).toBe('14');
  });

  test('take-home quantity stays a string', () => {
    const next = patchMedicineLine(
      { dosage: '1 tab', frequency_schedule: '1-0-0', duration: '', quantity: '' },
      'duration',
      '7 days',
      'quantity',
    );
    expect(next.quantity).toBe('7');
  });
});
