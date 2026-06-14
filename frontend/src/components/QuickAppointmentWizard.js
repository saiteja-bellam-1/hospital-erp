import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2, ChevronLeft } from 'lucide-react';
import { useToast } from '../hooks/use-toast';
import { errorDetail } from '../utils/apiErrors';
import PatientSearchPicker from './PatientSearchPicker';
import ReferralSelectWithCreate from './ReferralSelectWithCreate';
import PatientRegisterFormFields, {
  EMPTY_PATIENT_FORM,
  buildPatientPayload,
  validatePatientForm,
} from './PatientRegisterFormFields';
import AppointmentAvailabilityOverride from './AppointmentAvailabilityOverride';
import AppointmentTimeField from './AppointmentTimeField';
import {
  APPOINTMENT_OVERRIDE_DEFAULTS,
  isAppointmentSubmitDisabled,
  validateAppointmentBooking,
} from '../utils/appointmentBooking';

const EMPTY_APPOINTMENT = {
  doctor_id: '',
  appointment_date: new Date().toISOString().split('T')[0],
  appointment_time: '',
  duration_minutes: 10,
  appointment_type: 'consultation',
  reason: '',
  priority: 'normal',
  payment_status: 'paid',
  payment_method: 'cash',
  discount_amount: 0,
  payment_notes: '',
  referred_by: '',
  ...APPOINTMENT_OVERRIDE_DEFAULTS,
};

export default function QuickAppointmentWizard({ open, onOpenChange, onBooked }) {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [patientForm, setPatientForm] = useState(EMPTY_PATIENT_FORM);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [registerMode, setRegisterMode] = useState('register'); // default: new walk-in
  const [step1Loading, setStep1Loading] = useState(false);

  const [doctors, setDoctors] = useState([]);
  const [referralList, setReferralList] = useState([]);
  const [appointmentForm, setAppointmentForm] = useState(EMPTY_APPOINTMENT);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [availabilityChecking, setAvailabilityChecking] = useState(false);
  const [patientFeeInfo, setPatientFeeInfo] = useState({ is_new_patient: false, registration_fee: 0 });
  const [booking, setBooking] = useState(false);

  const reset = () => {
    setStep(1);
    setPatientForm(EMPTY_PATIENT_FORM);
    setSelectedPatient(null);
    setRegisterMode('register');
    setAppointmentForm(EMPTY_APPOINTMENT);
    setAvailableSlots([]);
    setPatientFeeInfo({ is_new_patient: false, registration_fee: 0 });
  };

  useEffect(() => {
    if (!open) {
      reset();
      return;
    }
    (async () => {
      try {
        const [docRes, refRes] = await Promise.all([
          axios.get('/api/appointments/doctors'),
          axios.get('/api/referrals'),
        ]);
        setDoctors(docRes.data || []);
        setReferralList(refRes.data || []);
      } catch {
        setDoctors([]);
        setReferralList([]);
      }
    })();
  }, [open]);

  const fetchPatientFeeInfo = async (patientUuid) => {
    try {
      const res = await axios.get(`/api/appointments/patient-fee-info/${patientUuid}`);
      setPatientFeeInfo(res.data);
    } catch {
      setPatientFeeInfo({ is_new_patient: false, registration_fee: 0 });
    }
  };

  const fetchAvailableSlots = async (doctorId, date) => {
    if (!doctorId || !date) {
      setAvailableSlots([]);
      return;
    }
    setAvailabilityChecking(true);
    try {
      const res = await axios.get(`/api/appointments/doctors/${doctorId}/available-slots`, {
        params: { appointment_date: date },
      });
      let slots = res.data?.available_slots || [];
      if (res.data?.default_consultation_duration) {
        setAppointmentForm((prev) => ({ ...prev, duration_minutes: res.data.default_consultation_duration }));
      }
      const today = new Date().toISOString().split('T')[0];
      if (date === today) {
        const now = new Date();
        const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        slots = slots.filter((slot) => slot.start_time >= currentTime);
      }
      setAvailableSlots(slots);
    } catch {
      setAvailableSlots([]);
    } finally {
      setAvailabilityChecking(false);
    }
  };

  const checkAvailability = async (doctorId, date, time, duration) => {
    try {
      const res = await axios.get(`/api/appointments/doctors/${doctorId}/availability`, {
        params: { appointment_date: date, appointment_time: time, duration_minutes: duration },
      });
      return res.data;
    } catch {
      return { is_available: false, reason: 'Could not verify availability' };
    }
  };

  const goToStep2 = async (patient) => {
    setSelectedPatient(patient);
    await fetchPatientFeeInfo(patient.patient_id);
    setStep(2);
    if (appointmentForm.doctor_id) {
      fetchAvailableSlots(appointmentForm.doctor_id, appointmentForm.appointment_date);
    }
  };

  const handleStep1Next = async () => {
    if (registerMode === 'search') {
      if (!selectedPatient) {
        toast({ variant: 'destructive', title: 'Select patient', description: 'Search and select a patient to continue.' });
        return;
      }
      await goToStep2(selectedPatient);
      return;
    }

    const err = validatePatientForm(patientForm);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      return;
    }

    setStep1Loading(true);
    try {
      const res = await axios.post('/api/patients/', buildPatientPayload(patientForm));
      toast({ title: 'Patient registered', description: `${res.data.first_name} ${res.data.last_name} registered.` });
      await goToStep2(res.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Registration failed', description: errorDetail(e) });
    } finally {
      setStep1Loading(false);
    }
  };

  const handleBook = async () => {
    if (!selectedPatient) return;
    const validationError = validateAppointmentBooking(appointmentForm, { selectedPatient: true });
    if (validationError) {
      toast({ variant: 'destructive', title: 'Missing fields', description: validationError });
      return;
    }

    setBooking(true);
    try {
      if (!appointmentForm.override_availability) {
        const check = await checkAvailability(
          appointmentForm.doctor_id,
          appointmentForm.appointment_date,
          appointmentForm.appointment_time,
          appointmentForm.duration_minutes
        );
        if (!check.is_available) {
          toast({ variant: 'destructive', title: 'Unavailable', description: check.reason || 'Slot not available' });
          setBooking(false);
          return;
        }
      }

      const res = await axios.post('/api/appointments/', {
        patient_id: selectedPatient.patient_id,
        ...appointmentForm,
      });
      toast({ title: 'Appointment booked', description: 'Patient registered and appointment scheduled.' });
      onOpenChange(false);
      onBooked?.(res.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Booking failed', description: errorDetail(e) });
    } finally {
      setBooking(false);
    }
  };

  const doctor = doctors.find((d) => d.id.toString() === String(appointmentForm.doctor_id));
  const baseFee = doctor?.consultation_fee_inr
    ? parseFloat(String(doctor.consultation_fee_inr).replace('₹', '').replace(',', '').trim()) || 0
    : 0;
  const consultFee = appointmentForm.appointment_type === 'followup' ? 0 : baseFee;
  const regFee = patientFeeInfo.is_new_patient ? patientFeeInfo.registration_fee : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Quick Appointment — Step {step} of 2: {step === 1 ? 'Patient' : 'Appointment'}
          </DialogTitle>
        </DialogHeader>

        {step === 1 ? (
          <div className="space-y-4">
            {registerMode === 'register' ? (
              <button
                type="button"
                className="text-sm text-blue-600 hover:underline"
                onClick={() => setRegisterMode('search')}
              >
                Patient already registered? Search instead
              </button>
            ) : (
              <button
                type="button"
                className="text-sm text-blue-600 hover:underline"
                onClick={() => { setRegisterMode('register'); setSelectedPatient(null); }}
              >
                Register a new patient instead
              </button>
            )}

            {registerMode === 'register' ? (
              <PatientRegisterFormFields form={patientForm} onChange={setPatientForm} />
            ) : (
              <PatientSearchPicker
                value={selectedPatient}
                onChange={setSelectedPatient}
                label="Find patient"
                required
              />
            )}

            <div className="flex gap-2 pt-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="button" className="flex-1" disabled={step1Loading} onClick={handleStep1Next}>
                {step1Loading ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Next: Book appointment'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm">
              <span className="font-medium text-green-900">
                {selectedPatient?.first_name} {selectedPatient?.last_name}
              </span>
              <span className="text-green-700 ml-2">{selectedPatient?.primary_phone}</span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Doctor *</Label>
                <Select
                  value={appointmentForm.doctor_id}
                  onValueChange={(value) => {
                    setAppointmentForm({ ...appointmentForm, doctor_id: value });
                    fetchAvailableSlots(value, appointmentForm.appointment_date);
                  }}
                >
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctors.map((d) => (
                      <SelectItem key={d.id} value={d.id.toString()}>
                        Dr. {d.first_name} {d.last_name} — {d.specialization || 'General'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Date *</Label>
                <Input
                  type="date"
                  value={appointmentForm.appointment_date}
                  min={new Date().toISOString().split('T')[0]}
                  onChange={(e) => {
                    setAppointmentForm({ ...appointmentForm, appointment_date: e.target.value });
                    if (appointmentForm.doctor_id) {
                      fetchAvailableSlots(appointmentForm.doctor_id, e.target.value);
                    }
                  }}
                />
              </div>
              <AppointmentTimeField
                appointmentTime={appointmentForm.appointment_time}
                overrideAvailability={appointmentForm.override_availability}
                availableSlots={availableSlots}
                availabilityChecking={availabilityChecking}
                doctorId={appointmentForm.doctor_id}
                appointmentDate={appointmentForm.appointment_date}
                onTimeChange={(value) => setAppointmentForm({ ...appointmentForm, appointment_time: value })}
              />
              <div>
                <Label>Type</Label>
                <Select
                  value={appointmentForm.appointment_type}
                  onValueChange={(v) => setAppointmentForm({ ...appointmentForm, appointment_type: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="consultation">Consultation</SelectItem>
                    <SelectItem value="followup">Follow-up</SelectItem>
                    <SelectItem value="checkup">Check-up</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Payment method</Label>
                <Select
                  value={appointmentForm.payment_method}
                  onValueChange={(v) => setAppointmentForm({ ...appointmentForm, payment_method: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['cash', 'card', 'upi', 'online', 'insurance', 'cheque'].map((m) => (
                      <SelectItem key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <AppointmentAvailabilityOverride
              className="md:col-span-2"
              overrideAvailability={appointmentForm.override_availability}
              overrideReason={appointmentForm.override_reason}
              onChange={(patch) => setAppointmentForm({ ...appointmentForm, ...patch })}
            />

            <div>
              <Label>Reason for visit</Label>
              <Input
                value={appointmentForm.reason}
                onChange={(e) => setAppointmentForm({ ...appointmentForm, reason: e.target.value })}
                placeholder="Brief description"
              />
            </div>

            <ReferralSelectWithCreate
              value={appointmentForm.referred_by}
              onValueChange={(name) => setAppointmentForm({ ...appointmentForm, referred_by: name })}
              referrals={referralList}
              onReferralsChange={setReferralList}
            />

            {appointmentForm.doctor_id && (
              <div className="bg-gray-50 rounded-lg p-3 border text-sm space-y-1">
                <p className="font-medium">Fee summary</p>
                {regFee > 0 && <p>Registration fee: ₹{regFee.toFixed(2)}</p>}
                <p>Consultation: ₹{consultFee.toFixed(2)}</p>
                <p className="font-semibold">Total: ₹{(regFee + consultFee).toFixed(2)}</p>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setStep(1)}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Back
              </Button>
              <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                className="flex-1"
                disabled={isAppointmentSubmitDisabled(appointmentForm, { loading: booking, selectedPatient: !!selectedPatient })}
                onClick={handleBook}
              >
                {booking ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Booking…</> : 'Book appointment'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
