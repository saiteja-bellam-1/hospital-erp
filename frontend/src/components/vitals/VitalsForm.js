import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Textarea } from '../ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import {
  Heart,
  Thermometer,
  Scale,
  Stethoscope,
  Save,
  Activity,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import { localDateString } from '../../utils/localDate';
import {
  buildVitalSignsPayload,
  showBmiOutput,
  showHeightInput,
  showWeightInput,
  useConfiguredVitalFields,
} from '../../hooks/useConfiguredVitalFields';

const emptyForm = () => ({
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
  recorded_date: localDateString(),
});

const getBMICategory = (bmi) => {
  const bmiValue = parseFloat(bmi);
  if (bmiValue < 18.5) return 'Underweight';
  if (bmiValue < 25) return 'Normal';
  if (bmiValue < 30) return 'Overweight';
  return 'Obese';
};

const VitalsForm = ({
  isOpen,
  onClose,
  selectedPatient,
  onSave,
  userRole = 'nurse',
  appointmentId = null,
}) => {
  const { toast } = useToast();
  const { vitalFields, isLoading: configLoading, isEnabled } = useConfiguredVitalFields();
  const [loading, setLoading] = useState(false);
  const [vitalsForm, setVitalsForm] = useState(emptyForm);

  useEffect(() => {
    if (vitalsForm.weight && vitalsForm.height) {
      const weightKg = parseFloat(vitalsForm.weight);
      const heightM = parseFloat(vitalsForm.height) / 100;
      if (weightKg > 0 && heightM > 0) {
        const bmi = (weightKg / (heightM * heightM)).toFixed(1);
        setVitalsForm((prev) => (prev.bmi === bmi ? prev : { ...prev, bmi }));
      }
    }
  }, [vitalsForm.weight, vitalsForm.height, vitalsForm.bmi]);

  useEffect(() => {
    if (isOpen) {
      setVitalsForm(emptyForm());
    }
  }, [isOpen, selectedPatient?.id, selectedPatient?.patient_id]);

  const resetForm = () => setVitalsForm(emptyForm());

  const handleSave = async () => {
    if (!selectedPatient) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const vitalsData = buildVitalSignsPayload(vitalsForm, vitalFields, {
        recordedBy: userRole,
      });

      const patientId =
        selectedPatient.patient_id ||
        selectedPatient.patient_uuid ||
        selectedPatient.id;

      if (!patientId) {
        toast({ variant: 'destructive', title: 'Error', description: 'Patient ID is missing' });
        return;
      }

      const response = await fetch('/api/patients/vitals', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          patient_id: patientId,
          vital_signs: JSON.stringify(vitalsData),
          notes: vitalsForm.notes,
          ...(appointmentId ? { appointment_id: appointmentId } : {}),
        }),
      });

      if (response.ok) {
        toast({ title: 'Success', description: 'Vitals recorded successfully!' });
        if (onSave) onSave(vitalsData);
        onClose();
        resetForm();
      } else {
        const err = await response.json().catch(() => ({}));
        toast({
          variant: 'destructive',
          title: 'Error',
          description: err.detail || 'Failed to save vitals',
        });
      }
    } catch (error) {
      console.error('Error saving vitals:', error);
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save vitals. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  const showCardio = isEnabled('blood_pressure') || isEnabled('heart_rate');
  const showRespiratory = isEnabled('respiratory_rate') || isEnabled('spo2');
  const showGeneral = isEnabled('temperature') || isEnabled('pain_scale');
  const showPhysical =
    showHeightInput(vitalFields) || showWeightInput(vitalFields) || showBmiOutput(vitalFields);

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto" formNav="grid">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Record Vital Signs - {selectedPatient?.first_name} {selectedPatient?.last_name}
          </DialogTitle>
        </DialogHeader>
        {configLoading ? (
          <p className="text-sm text-muted-foreground py-6">Loading vitals configuration…</p>
        ) : (
          <form
            className="space-y-6"
            onSubmit={(e) => {
              e.preventDefault();
              handleSave();
            }}
          >
            {(showCardio || showRespiratory) && (
              <div className={`grid gap-6 ${showCardio && showRespiratory ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'}`}>
                {showCardio && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Heart className="h-5 w-5 text-red-500" />
                        Cardiovascular
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {isEnabled('blood_pressure') && (
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <Label>Systolic BP (mmHg)</Label>
                            <Input
                              type="number"
                              placeholder="120"
                              value={vitalsForm.blood_pressure_systolic}
                              onChange={(e) =>
                                setVitalsForm((prev) => ({
                                  ...prev,
                                  blood_pressure_systolic: e.target.value,
                                }))
                              }
                            />
                          </div>
                          <div>
                            <Label>Diastolic BP (mmHg)</Label>
                            <Input
                              type="number"
                              placeholder="80"
                              value={vitalsForm.blood_pressure_diastolic}
                              onChange={(e) =>
                                setVitalsForm((prev) => ({
                                  ...prev,
                                  blood_pressure_diastolic: e.target.value,
                                }))
                              }
                            />
                          </div>
                        </div>
                      )}
                      {isEnabled('heart_rate') && (
                        <div>
                          <Label>Heart Rate (BPM)</Label>
                          <Input
                            type="number"
                            placeholder="72"
                            value={vitalsForm.heart_rate}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({ ...prev, heart_rate: e.target.value }))
                            }
                          />
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {showRespiratory && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Stethoscope className="h-5 w-5 text-blue-500" />
                        Respiratory
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {isEnabled('respiratory_rate') && (
                        <div>
                          <Label>Respiratory Rate (per min)</Label>
                          <Input
                            type="number"
                            placeholder="16"
                            value={vitalsForm.respiratory_rate}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({
                                ...prev,
                                respiratory_rate: e.target.value,
                              }))
                            }
                          />
                        </div>
                      )}
                      {isEnabled('spo2') && (
                        <div>
                          <Label>Oxygen Saturation (%)</Label>
                          <Input
                            type="number"
                            placeholder="98"
                            min="0"
                            max="100"
                            value={vitalsForm.oxygen_saturation}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({
                                ...prev,
                                oxygen_saturation: e.target.value,
                              }))
                            }
                          />
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            )}

            {(showGeneral || showPhysical) && (
              <div className={`grid gap-6 ${showGeneral && showPhysical ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'}`}>
                {showGeneral && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Thermometer className="h-5 w-5 text-orange-500" />
                        General
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {isEnabled('temperature') && (
                        <div>
                          <Label>Temperature (°F)</Label>
                          <Input
                            type="number"
                            step="0.1"
                            placeholder="98.6"
                            value={vitalsForm.temperature}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({ ...prev, temperature: e.target.value }))
                            }
                          />
                        </div>
                      )}
                      {isEnabled('pain_scale') && (
                        <div>
                          <Label>Pain Scale (0-10)</Label>
                          <Select
                            value={vitalsForm.pain_scale}
                            onValueChange={(value) =>
                              setVitalsForm((prev) => ({ ...prev, pain_scale: value }))
                            }
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select pain level" />
                            </SelectTrigger>
                            <SelectContent>
                              {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((level) => (
                                <SelectItem key={level} value={level.toString()}>
                                  {level} -{' '}
                                  {level === 0
                                    ? 'No pain'
                                    : level <= 3
                                      ? 'Mild'
                                      : level <= 6
                                        ? 'Moderate'
                                        : 'Severe'}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {showPhysical && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Scale className="h-5 w-5 text-green-500" />
                        Physical Measurements
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {showWeightInput(vitalFields) && (
                        <div>
                          <Label>Weight (kg)</Label>
                          <Input
                            type="number"
                            step="0.1"
                            placeholder="70.0"
                            value={vitalsForm.weight}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({ ...prev, weight: e.target.value }))
                            }
                          />
                        </div>
                      )}
                      {showHeightInput(vitalFields) && (
                        <div>
                          <Label>Height (cm)</Label>
                          <Input
                            type="number"
                            placeholder="170"
                            value={vitalsForm.height}
                            onChange={(e) =>
                              setVitalsForm((prev) => ({ ...prev, height: e.target.value }))
                            }
                          />
                        </div>
                      )}
                      {showBmiOutput(vitalFields) && vitalsForm.bmi && (
                        <div>
                          <Label>BMI (calculated)</Label>
                          <Input
                            value={`${vitalsForm.bmi} - ${getBMICategory(vitalsForm.bmi)}`}
                            disabled
                            className="bg-gray-50"
                          />
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            )}

            <div>
              <Label>Additional Notes</Label>
              <Textarea
                value={vitalsForm.notes}
                onChange={(e) => setVitalsForm((prev) => ({ ...prev, notes: e.target.value }))}
                placeholder="Any additional observations or notes..."
                rows={3}
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading || configLoading}>
                <Save className="h-4 w-4 mr-2" />
                {loading ? 'Saving...' : 'Save Vitals'}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default VitalsForm;
