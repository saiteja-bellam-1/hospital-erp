import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../../components/ui/dialog';
import { Textarea } from '../../../components/ui/textarea';
import { useToast } from '../../../hooks/use-toast';
import { ConfirmDialog } from '../../../components/ui/confirm-dialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import ReferralSelectWithCreate from '../../../components/ReferralSelectWithCreate';
import AppointmentAvailabilityOverride from '../../../components/AppointmentAvailabilityOverride';
import AppointmentTimeField from '../../../components/AppointmentTimeField';
import {
  APPOINTMENT_OVERRIDE_DEFAULTS,
  buildAppointmentCreatePayload,
  isAppointmentSubmitDisabled,
  validateAppointmentBooking,
} from '../../../utils/appointmentBooking';
import { localDateString } from '../../../utils/localDate';
import { printPdfFromUrl } from '../../../utils/printPdf';
import {
  Calendar,
  Clock,
  User,
  Phone,
  Receipt,
  RefreshCw,
  CalendarPlus,
  Eye,
  Printer,
  Search,
  Filter,
  LogIn,
  LogOut,
  XCircle,
  CalendarClock,
  Hash,
  Play,
  UserX,
  FileText,
  History,
  TestTube,
  Download,
  Package
} from 'lucide-react';

const ReceptionAppointmentsPage = () => {
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [confirmState, setConfirmState] = useState({ open: false });
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [doctors, setDoctors] = useState([]);
  const [allAppointments, setAllAppointments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [availabilityChecking, setAvailabilityChecking] = useState(false);

  // Patient search state

  // Prescription dialog state
  const [showPrescriptionDialog, setShowPrescriptionDialog] = useState(false);
  const [prescriptionPdfUrl, setPrescriptionPdfUrl] = useState(null);
  const [prescriptionData, setPrescriptionData] = useState(null);
  // Lab payment dialog state
  const [showLabPaymentDialog, setShowLabPaymentDialog] = useState(false);
  const [pendingLabOrders, setPendingLabOrders] = useState([]);
  const [labPaymentLoading, setLabPaymentLoading] = useState(false);
  const [labPaymentMethod, setLabPaymentMethod] = useState('cash');
  const [labBillPdfUrl, setLabBillPdfUrl] = useState(null);
  const [labBillOrderIds, setLabBillOrderIds] = useState([]);
  const [showLabBillPreview, setShowLabBillPreview] = useState(false);

  // Referrals
  const [referralList, setReferralList] = useState([]);
  useEffect(() => {
    const fetchRefs = async () => {
      try {
        const t = localStorage.getItem('token');
        const res = await fetch('/api/referrals', { headers: { Authorization: `Bearer ${t}` } });
        if (res.ok) setReferralList(await res.json());
      } catch {}
    };
    fetchRefs();
  }, []);

  // Dialogs
  const [showAppointmentDialog, setShowAppointmentDialog] = useState(false);
  const [showBillPreviewDialog, setShowBillPreviewDialog] = useState(false);
  const [currentBill, setCurrentBill] = useState(null);
  const [billPdfUrl, setBillPdfUrl] = useState(null);
  const [currentBillAppointmentId, setCurrentBillAppointmentId] = useState(null);

  // Cancel dialog
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [cancelAppointmentId, setCancelAppointmentId] = useState(null);
  const [cancelReason, setCancelReason] = useState('');

  // Reschedule dialog
  const [showRescheduleDialog, setShowRescheduleDialog] = useState(false);
  const [rescheduleAppointmentId, setRescheduleAppointmentId] = useState(null);
  const [rescheduleForm, setRescheduleForm] = useState({ new_date: '', new_time: '' });
  const [rescheduleSlots, setRescheduleSlots] = useState([]);
  const [rescheduleDoctor, setRescheduleDoctor] = useState(null);

  // Notes dialog
  const [showNotesDialog, setShowNotesDialog] = useState(false);
  const [notesAppointmentId, setNotesAppointmentId] = useState(null);
  const [notesText, setNotesText] = useState('');

  // Patient fee info
  const [patientFeeInfo, setPatientFeeInfo] = useState({ is_new_patient: false, registration_fee: 0 });

  // Search and filter states
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDate, setFilterDate] = useState(localDateString());
  const [filterDoctor, setFilterDoctor] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');

  // Forms
  const [appointmentForm, setAppointmentForm] = useState({
    doctor_id: '',
    appointment_date: localDateString(),
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
  });

  // Load initial data
  useEffect(() => {
    fetchDoctors();
    fetchTodayAppointments();
  }, []);

  // Deep-link: ?action=schedule&patientUuid=… (e.g. from Patients page "Book Appointment")
  useEffect(() => {
    const action = searchParams.get('action');
    if (action !== 'schedule') return;

    const patientUuid = searchParams.get('patientUuid');
    setShowAppointmentDialog(true);
    setSearchParams({}, { replace: true });

    if (!patientUuid) return;

    (async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`/api/patients/${encodeURIComponent(patientUuid)}`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const patient = await response.json();
          setSelectedPatient(patient);
          fetchPatientFeeInfo(patient.patient_id);
        } else {
          toast({
            variant: 'destructive',
            title: 'Patient not found',
            description: 'Could not load the selected patient. Please search again.',
          });
        }
      } catch {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Could not load the selected patient.',
        });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Fetch appointments when filter date changes
  useEffect(() => {
    if (filterDate) {
      fetchAppointmentsByDate(filterDate);
    }
  }, [filterDate]);

  const fetchDoctors = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/doctors', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const data = await response.json();
        setDoctors(data);
      }
    } catch (error) {
      console.error('Error fetching doctors:', error);
    }
  };

  const fetchTodayAppointments = () => {
    fetchAppointmentsByDate(localDateString());
  };

  const fetchAppointmentsByDate = async (date) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/?date_from=${date}&date_to=${date}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const data = await response.json();
        setAllAppointments(Array.isArray(data) ? data : []);
      } else {
        console.error('Failed to fetch appointments:', response.status, response.statusText);
        setAllAppointments([]);
      }
    } catch (error) {
      console.error('Error fetching appointments:', error);
      setAllAppointments([]);
    }
  };

  const displayedAppointments = useMemo(() => {
    let appointments = allAppointments;
    if (filterDoctor && filterDoctor !== 'all') {
      appointments = appointments.filter(apt => apt.doctor_id.toString() === filterDoctor);
    }
    if (filterStatus && filterStatus !== 'all') {
      appointments = appointments.filter(apt => apt.status === filterStatus);
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      appointments = appointments.filter(apt =>
        apt.patient_name?.toLowerCase().includes(q) ||
        apt.doctor_name?.toLowerCase().includes(q) ||
        apt.appointment_number?.toLowerCase().includes(q)
      );
    }
    return appointments;
  }, [allAppointments, filterDoctor, filterStatus, searchTerm]);

  const refreshAfterBooking = async (bookedDate) => {
    setFilterDate(bookedDate);
    setSearchTerm('');
    setFilterDoctor('all');
    setFilterStatus('all');
    await fetchAppointmentsByDate(bookedDate);
  };

  const searchPatientByPhone = async (phone) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/patients/phone/${phone}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const patient = await response.json();
        setSelectedPatient(patient);
        fetchPatientFeeInfo(patient.patient_id);
        return patient;
      }
    } catch (error) {
      console.error('Error searching patient:', error);
    }
    return null;
  };

  const fetchPatientFeeInfo = async (patientUuid) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/patient-fee-info/${patientUuid}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setPatientFeeInfo(data);
      }
    } catch (error) {
      console.error('Error fetching patient fee info:', error);
    }
  };

  const handlePatientSelected = (patient) => {
    setSelectedPatient(patient);
    if (patient?.patient_id) fetchPatientFeeInfo(patient.patient_id);
  };

  // Prescription preview
  const showPrescriptionPreview = async (appointmentId, patientUuid) => {
    try {
      const token = localStorage.getItem('token');
      // Fetch prescriptions for this patient
      const response = await fetch(`/api/prescriptions-simple/?patient_id=${patientUuid}&limit=5`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const prescriptions = await response.json();
        if (prescriptions.length === 0) {
          toast({ title: 'Info', description: 'No prescriptions found for this patient.' });
          return;
        }
        // Get the latest prescription
        const latest = prescriptions[0];
        setPrescriptionData(latest);

        // Fetch PDF
        await fetchPrescriptionPdf(latest.prescription_id);
      }
    } catch (error) {
      console.error('Error fetching prescription:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error loading prescription' });
    }
  };

  const printPrescription = () => {
    if (!prescriptionPdfUrl) return;
    printPdfFromUrl(prescriptionPdfUrl, {
      onError: (message) => toast({ variant: 'destructive', title: 'Print Failed', description: message }),
    });
  };

  const printBlankPrescription = async (appointment) => {
    const params = {
      doctor_id: appointment.doctor_id,
      appointment_id: appointment.id,
    };
    if (appointment.patient_uuid) {
      params.patient_id = appointment.patient_uuid;
    }
    await printPdfFromUrl('/api/prescriptions-simple/blank/download', {
      params,
      onError: (message) => toast({ variant: 'destructive', title: 'Print Failed', description: message }),
    });
  };

  const fetchPrescriptionPdf = async (prescriptionId) => {
    try {
      const token = localStorage.getItem('token');
      const pdfResponse = await fetch(`/api/prescriptions-simple/${prescriptionId}/download`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (pdfResponse.ok) {
        const blob = await pdfResponse.blob();
        if (prescriptionPdfUrl) window.URL.revokeObjectURL(prescriptionPdfUrl);
        const url = window.URL.createObjectURL(blob);
        setPrescriptionPdfUrl(url);
        setShowPrescriptionDialog(true);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to load prescription PDF' });
      }
    } catch (error) {
      console.error('Error fetching PDF:', error);
    }
  };

  const closePrescriptionPreview = () => {
    setShowPrescriptionDialog(false);
    if (prescriptionPdfUrl) {
      window.URL.revokeObjectURL(prescriptionPdfUrl);
      setPrescriptionPdfUrl(null);
    }
    setPrescriptionData(null);
  };

  // Lab Payment functions
  const [allLabOrders, setAllLabOrders] = useState([]);

  const openLabPaymentDialog = async (patientId) => {
    setLabPaymentLoading(true);
    setShowLabPaymentDialog(true);
    setPendingLabOrders([]);
    setAllLabOrders([]);
    try {
      const token = localStorage.getItem('token');
      // Fetch all lab orders for the patient — many orders (consultation,
      // walk-in) are not linked to appointment_id, so do not filter by apt.
      const res = await fetch(`/api/lab/orders?patient_id=${patientId}&reception_view=true`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const orders = await res.json();
        setPendingLabOrders(orders.filter((o) => o.payment_status !== 'paid' && o.status !== 'cancelled'));
        setAllLabOrders(Array.isArray(orders) ? orders : []);
      }
    } catch (err) {
      console.error('Failed to fetch lab orders:', err);
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const labReportOrders = allLabOrders.filter((o) => o.has_report);
  const labInProgressOrders = allLabOrders.filter(
    (o) => o.payment_status === 'paid' && o.status !== 'completed' && o.status !== 'cancelled'
  );

  const collectLabPayment = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/${orderId}/payment`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method: labPaymentMethod })
      });
      if (res.ok) {
        setPendingLabOrders(prev => prev.filter(o => o.id !== orderId));
      } else {
        const err = await res.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Payment failed' });
      }
    } catch (err) {
      console.error('Payment failed:', err);
    }
  };

  const collectAllLabPayments = async () => {
    if (pendingLabOrders.length === 0) return;
    if (labPaymentLoading) return;
    const patientId = pendingLabOrders[0].patient_id;
    setLabPaymentLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/patient/${patientId}/bill`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method: labPaymentMethod })
      });
      if (res.ok) {
        const orderIdsHeader = res.headers.get('X-Order-Ids');
        const ids = orderIdsHeader ? orderIdsHeader.split(',').map(Number) : [];
        setLabBillOrderIds(ids);

        const blob = await res.blob();
        if (labBillPdfUrl) window.URL.revokeObjectURL(labBillPdfUrl);
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
        setLabBillPdfUrl(url);
        setShowLabBillPreview(true);
        setPendingLabOrders([]);
        toast({ title: 'Success', description: 'Lab bill generated' });
        fetchTodayAppointments();
      } else {
        const err = await res.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Bill generation failed' });
      }
    } catch (err) {
      console.error('Bill generation failed:', err);
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate lab bill' });
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const downloadLabReport = async (reportId, orderNumber, packageBookingId = null) => {
    try {
      const token = localStorage.getItem('token');
      const url = packageBookingId
        ? `/api/lab/reports/package/${packageBookingId}/download`
        : `/api/lab/reports/${reportId}/download`;
      const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = packageBookingId ? `${orderNumber}_report.pdf` : `lab_report_${orderNumber}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to download report' });
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to download report' });
    }
  };

  const createAppointment = async () => {
    if (!selectedPatient) return;

    const validationError = validateAppointmentBooking(appointmentForm, { selectedPatient: true });
    if (validationError) {
      toast({ variant: 'destructive', title: 'Cannot book', description: validationError });
      return;
    }

    // Check availability before booking (skipped when override is on — backend
    // still blocks double-booking)
    setLoading(true);
    try {
      if (!appointmentForm.override_availability && appointmentForm.appointment_time) {
        const availabilityCheck = await checkAvailability(
          appointmentForm.doctor_id,
          appointmentForm.appointment_date,
          appointmentForm.appointment_time,
          appointmentForm.duration_minutes
        );

        if (!availabilityCheck.is_available) {
          toast({ variant: 'destructive', title: 'Error', description: `Cannot book appointment: ${availabilityCheck.reason}` });
          setLoading(false);
          return;
        }
      }

      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(buildAppointmentCreatePayload(appointmentForm, {
          patient_id: selectedPatient.patient_id,
        }))
      });

      if (response.ok) {
        const appointmentData = await response.json();
        const bookedDate = appointmentForm.appointment_date;
        setShowAppointmentDialog(false);
        await refreshAfterBooking(bookedDate);
        setAppointmentForm({
          doctor_id: '',
          appointment_date: localDateString(),
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
        });
        setAvailableSlots([]);
        setSelectedPatient(null);
        setPatientFeeInfo({ is_new_patient: false, registration_fee: 0 });

        // Show bill preview if consultation fee exists or registration fee charged
        if (appointmentData.consultation_fee > 0 || appointmentData.registration_fee > 0) {
          showBillPreview(appointmentData.id);
        } else {
          toast({ title: 'Success', description: 'Appointment booked successfully!' });
        }
      } else {
        const errorData = await response.json();
        console.error('Appointment creation failed:', errorData);
        toast({ variant: 'destructive', title: 'Error', description: `Failed to book appointment: ${errorData.detail || 'Unknown error'}` });
      }
    } catch (error) {
      console.error('Error creating appointment:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error creating appointment. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  // Bill preview functions
  const showBillPreview = async (appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      setCurrentBillAppointmentId(appointmentId);

      // Fetch bill data
      const billResponse = await fetch(`/api/appointments/${appointmentId}/bill`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (billResponse.ok) {
        const billData = await billResponse.json();
        setCurrentBill(billData);

        // Fetch PDF for preview
        const pdfResponse = await fetch(`/api/appointments/${appointmentId}/bill/download`, {
          headers: { Authorization: `Bearer ${token}` }
        });

        if (pdfResponse.ok) {
          if (billPdfUrl) window.URL.revokeObjectURL(billPdfUrl);
          const blob = await pdfResponse.blob();
          const url = window.URL.createObjectURL(blob);
          setBillPdfUrl(url);
          setShowBillPreviewDialog(true);
        } else {
          const err = await pdfResponse.json().catch(() => ({}));
          toast({
            variant: 'destructive',
            title: 'Error',
            description: err.detail || 'Failed to generate bill PDF',
          });
        }
      } else {
        const err = await billResponse.json().catch(() => ({}));
        toast({
          variant: 'destructive',
          title: 'Error',
          description: err.detail || 'Failed to load bill',
        });
      }
    } catch (error) {
      console.error('Error fetching bill:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load bill preview' });
    }
  };

  const printBill = () => {
    if (billPdfUrl) {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
      iframe.src = billPdfUrl;
      
      iframe.onload = () => {
        iframe.contentWindow.print();
        setTimeout(() => {
          document.body.removeChild(iframe);
        }, 1000);
      };
    }
  };

  const closeBillPreview = () => {
    setShowBillPreviewDialog(false);
    if (billPdfUrl) {
      window.URL.revokeObjectURL(billPdfUrl);
      setBillPdfUrl(null);
    }
    setCurrentBill(null);
  };

  // Check-in handler
  const handleCheckIn = async (appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${appointmentId}/check-in`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        toast({ title: 'Success', description: `Patient checked in! Token #${data.token_number}` });
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Check-in failed' });
      }
    } catch (error) {
      console.error('Check-in error:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error during check-in' });
    }
  };

  // Boost / Skip / Recall handlers (token queue)
  const handleQueueAction = async (action, doctorId, appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/queue/${doctorId}/${action}/${appointmentId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        toast({ title: 'Queue updated', description: data.message || `${action} complete` });
        fetchAppointmentsByDate(filterDate);
      } else {
        const msg = typeof data.detail === 'string' ? data.detail : `Failed to ${action}`;
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } catch (error) {
      console.error(`Queue ${action} error:`, error);
      toast({ variant: 'destructive', title: 'Error', description: `Failed to ${action}` });
    }
  };

  // Check-out handler
  const handleCheckOut = async (appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${appointmentId}/check-out`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        toast({ title: 'Success', description: 'Patient checked out successfully' });
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Check-out failed' });
      }
    } catch (error) {
      console.error('Check-out error:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error during check-out' });
    }
  };

  // Cancel handler
  const openCancelDialog = (appointmentId) => {
    setCancelAppointmentId(appointmentId);
    setCancelReason('');
    setShowCancelDialog(true);
  };

  const handleCancelAppointment = async () => {
    if (!cancelReason.trim()) {
      toast({ variant: 'destructive', title: 'Validation', description: 'Please provide a reason for cancellation' });
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${cancelAppointmentId}/cancel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: cancelReason })
      });
      if (response.ok) {
        toast({ title: 'Success', description: 'Appointment cancelled' });
        setShowCancelDialog(false);
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Cancel failed' });
      }
    } catch (error) {
      console.error('Cancel error:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error cancelling appointment' });
    }
  };

  // Reschedule handler
  const openRescheduleDialog = (appointment) => {
    setRescheduleAppointmentId(appointment.id);
    setRescheduleDoctor(appointment.doctor_id);
    setRescheduleForm({ new_date: '', new_time: '' });
    setRescheduleSlots([]);
    setShowRescheduleDialog(true);
  };

  const fetchRescheduleSlots = async (doctorId, newDate) => {
    if (!doctorId || !newDate) return;
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/appointments/doctors/${doctorId}/available-slots?appointment_date=${newDate}`,
        { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const data = await response.json();
        let slots = data.available_slots || [];

        // Filter out past time slots if the selected date is today
        const today = localDateString();
        if (newDate === today) {
          const now = new Date();
          const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
          slots = slots.filter(slot => slot.start_time >= currentTime);
        }

        setRescheduleSlots(slots);
      }
    } catch (error) {
      console.error('Error fetching reschedule slots:', error);
    }
  };

  const handleReschedule = async () => {
    if (!rescheduleForm.new_date || !rescheduleForm.new_time) {
      toast({ variant: 'destructive', title: 'Validation', description: 'Please select a new date and time' });
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${rescheduleAppointmentId}/reschedule`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(rescheduleForm)
      });
      if (response.ok) {
        const data = await response.json();
        toast({ title: 'Success', description: `Appointment rescheduled! New appointment: ${data.new_appointment.appointment_number}` });
        setShowRescheduleDialog(false);
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Reschedule failed' });
      }
    } catch (error) {
      console.error('Reschedule error:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error rescheduling appointment' });
    }
  };

  // Start consultation handler
  const handleStartConsultation = async (appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${appointmentId}/start-consultation`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Failed to start consultation' });
      }
    } catch (error) {
      console.error('Start consultation error:', error);
    }
  };

  // No-show handler
  const handleNoShow = (appointmentId) => {
    setConfirmState({
      open: true,
      title: 'Mark No-Show',
      description: 'Mark this patient as no-show?',
      onConfirm: async () => {
        setConfirmState({ open: false });
        try {
          const token = localStorage.getItem('token');
          const response = await fetch(`/api/appointments/${appointmentId}/no-show`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
          });
          if (response.ok) {
            fetchAppointmentsByDate(filterDate);
          } else {
            const err = await response.json();
            toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Failed to mark no-show' });
          }
        } catch (error) {
          console.error('No-show error:', error);
        }
      }
    });
  };

  // Notes handlers
  const openNotesDialog = (appointment) => {
    setNotesAppointmentId(appointment.id);
    setNotesText(appointment.notes || '');
    setShowNotesDialog(true);
  };

  const handleSaveNotes = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${notesAppointmentId}/notes`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notesText })
      });
      if (response.ok) {
        setShowNotesDialog(false);
        fetchAppointmentsByDate(filterDate);
      } else {
        const err = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Failed to save notes' });
      }
    } catch (error) {
      console.error('Save notes error:', error);
    }
  };

  const formatTime = (timeStr) => {
    if (!timeStr) return '';
    try {
      const [hours, minutes] = timeStr.split(':');
      const h = parseInt(hours);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const h12 = h % 12 || 12;
      return `${h12}:${minutes} ${ampm}`;
    } catch {
      return timeStr;
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      'scheduled': 'bg-blue-100 text-blue-800',
      'confirmed': 'bg-green-100 text-green-800',
      'in_progress': 'bg-yellow-100 text-yellow-800',
      'completed': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800',
      'no_show': 'bg-red-100 text-red-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const clearFilters = () => {
    setSearchTerm('');
    setFilterDoctor('all');
    setFilterStatus('all');
    setFilterDate(localDateString());
  };

  // Check doctor availability and fetch available slots
  const fetchAvailableSlots = async (doctorId, date) => {
    if (!doctorId || !date) {
      setAvailableSlots([]);
      return;
    }

    setAvailabilityChecking(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/appointments/doctors/${doctorId}/available-slots?appointment_date=${date}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        let slots = data.available_slots || [];

        // Set form duration from doctor's configured duration
        if (data.default_consultation_duration) {
          setAppointmentForm(prev => ({ ...prev, duration_minutes: data.default_consultation_duration }));
        }

        // Filter out past time slots if the selected date is today
        const today = localDateString();
        if (date === today) {
          const now = new Date();
          const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
          slots = slots.filter(slot => slot.start_time >= currentTime);
        }

        setAvailableSlots(slots);
      } else {
        console.error('Failed to fetch available slots');
        setAvailableSlots([]);
      }
    } catch (error) {
      console.error('Error fetching available slots:', error);
      setAvailableSlots([]);
    } finally {
      setAvailabilityChecking(false);
    }
  };

  const checkAvailability = async (doctorId, date, time, duration) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/appointments/doctors/${doctorId}/availability?appointment_date=${date}&appointment_time=${time}&duration_minutes=${duration}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        return data;
      }
      return { is_available: false, reason: 'Unable to check availability' };
    } catch (error) {
      console.error('Error checking availability:', error);
      return { is_available: false, reason: 'Network error' };
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Appointment Management</h1>
          <p className="text-gray-600">Schedule and manage patient appointments</p>
        </div>
        <div className="flex space-x-3">
          <Button onClick={fetchTodayAppointments} variant="outline" className="flex items-center space-x-2">
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </Button>
          <Dialog open={showAppointmentDialog} onOpenChange={setShowAppointmentDialog}>
            <DialogTrigger asChild>
              <Button
                className="flex items-center space-x-2"
                onClick={() => setSelectedPatient(null)}
              >
                <CalendarPlus className="h-4 w-4" />
                <span>Schedule Appointment</span>
              </Button>
            </DialogTrigger>
          </Dialog>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <div>
              <Label>Search</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="Search appointments..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div>
              <Label>Date</Label>
              <Input
                type="date"
                value={filterDate}
                onChange={(e) => setFilterDate(e.target.value)}
              />
            </div>
            <div>
              <Label>Doctor</Label>
              <Select value={filterDoctor} onValueChange={setFilterDoctor}>
                <SelectTrigger>
                  <SelectValue placeholder="All Doctors" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Doctors</SelectItem>
                  {doctors.map((doctor) => (
                    <SelectItem key={doctor.id} value={doctor.id.toString()}>
                      Dr. {doctor.first_name} {doctor.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Status</Label>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger>
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="scheduled">Scheduled</SelectItem>
                  <SelectItem value="confirmed">Confirmed</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                  <SelectItem value="no_show">No Show</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button variant="outline" onClick={clearFilters} className="w-full">
                Clear Filters
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Appointments List */}
      <Card>
        <CardHeader>
          <CardTitle>
            Appointments for {new Date(filterDate).toLocaleDateString()} ({displayedAppointments.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {displayedAppointments.length === 0 ? (
            <div className="text-center py-8">
              <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-500">No appointments found for the selected criteria</p>
            </div>
          ) : (
            <div className="space-y-3">
              {displayedAppointments.map((appointment) => (
                <div key={appointment.id} className="border border-gray-200 rounded-xl overflow-hidden hover:border-gray-300 transition-colors">
                  {/* Top row: Patient info */}
                  <div className="px-4 py-3 flex items-start justify-between gap-4">
                    <div className="flex-1 grid grid-cols-1 md:grid-cols-4 gap-x-6 gap-y-2 min-w-0">
                      <div>
                        <div className="flex items-center gap-2 mb-0.5">
                          {appointment.token_number && (
                            <span className="inline-flex flex-col items-center justify-center w-10 h-10 rounded-full bg-blue-700 text-white shadow-sm ring-2 ring-blue-200 flex-shrink-0 leading-none" title={`Token #${appointment.token_number}`}>
                              <span className="text-[8px] uppercase tracking-wide opacity-80">Tok</span>
                              <span className="font-bold text-sm">{appointment.token_number}</span>
                            </span>
                          )}
                          <span className="font-semibold text-gray-900 truncate">{appointment.patient_name}</span>
                        </div>
                        <p className={`text-xs text-gray-500 ${appointment.token_number ? 'pl-12' : ''}`}>#{appointment.appointment_number}</p>
                      </div>

                      <div>
                        <p className="font-medium text-gray-800 truncate">{appointment.doctor_name}</p>
                        <p className="text-xs text-gray-500">{appointment.appointment_type}</p>
                      </div>

                      <div>
                        <p className="font-medium text-gray-800">{formatTime(appointment.appointment_time)}</p>
                        <div className="flex flex-wrap items-center gap-1 mt-0.5">
                          <Badge className={getStatusBadge(appointment.status)}>
                            {appointment.status.replace('_', ' ')}
                          </Badge>
                          {appointment.override_availability && (
                            <Badge variant="outline" className="text-amber-700 border-amber-300 bg-amber-50">
                              Override
                            </Badge>
                          )}
                        </div>
                        {appointment.cancellation_reason && (
                          <p className="text-xs text-red-500 mt-0.5 truncate" title={appointment.cancellation_reason}>Reason: {appointment.cancellation_reason}</p>
                        )}
                      </div>

                      <div>
                        {(appointment.consultation_fee > 0 || appointment.registration_fee > 0) && (
                          <div>
                            <p className="font-semibold text-green-700">₹{appointment.final_amount}</p>
                            {appointment.registration_fee > 0 && (
                              <p className="text-xs text-blue-600">incl. reg. ₹{appointment.registration_fee}</p>
                            )}
                            <Badge variant={appointment.payment_status === 'paid' ? 'success' : 'secondary'} className="mt-0.5">
                              {appointment.payment_status}
                            </Badge>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Bottom row: Action buttons — text-first, clean layout */}
                  <div className="px-4 py-2 bg-gray-50/80 border-t border-gray-100 flex items-center gap-2 flex-wrap">
                    {/* Token queue state badges */}
                    {appointment.token_status === 'skipped' && (
                      <Badge variant="secondary" className="h-6 text-[10px] bg-amber-100 text-amber-800">SKIPPED</Badge>
                    )}
                    {appointment.priority_boost > 0 && (
                      <Badge className="h-6 text-[10px] bg-red-600 text-white">PRIORITY</Badge>
                    )}

                    {/* Token queue actions — only meaningful after check-in */}
                    {appointment.checked_in_at && !['completed', 'cancelled', 'no_show'].includes(appointment.status) && (
                      <>
                        {!appointment.priority_boost && (
                          <Button size="sm" variant="outline" className="h-7 px-3 text-xs text-red-700 border-red-300"
                                  onClick={() => handleQueueAction('boost', appointment.doctor_id, appointment.id)}>
                            Boost
                          </Button>
                        )}
                        {appointment.token_status === 'skipped' && (
                          <Button size="sm" variant="outline" className="h-7 px-3 text-xs text-amber-700 border-amber-300"
                                  onClick={() => handleQueueAction('recall', appointment.doctor_id, appointment.id)}>
                            Recall
                          </Button>
                        )}
                      </>
                    )}

                    {/* Primary action — contextual */}
                    {appointment.status === 'scheduled' && !appointment.checked_in_at && (
                      <Button size="sm" className="h-7 px-3 text-xs bg-green-600 hover:bg-green-700 text-white" onClick={() => handleCheckIn(appointment.id)}>
                        Check In
                      </Button>
                    )}
                    {appointment.checked_in_at && appointment.status === 'confirmed' && (
                      <Button size="sm" className="h-7 px-3 text-xs bg-blue-600 hover:bg-blue-700 text-white" onClick={() => handleStartConsultation(appointment.id)}>
                        Start Consultation
                      </Button>
                    )}
                    {appointment.status === 'in_progress' && (
                      <Button size="sm" className="h-7 px-3 text-xs bg-orange-500 hover:bg-orange-600 text-white" onClick={() => handleCheckOut(appointment.id)}>
                        Check Out
                      </Button>
                    )}

                    {/* Secondary actions */}
                    {['scheduled', 'confirmed'].includes(appointment.status) && (
                      <Button size="sm" variant="outline" className="h-7 px-3 text-xs text-gray-700" onClick={() => openRescheduleDialog(appointment)}>
                        Reschedule
                      </Button>
                    )}
                    {['scheduled', 'confirmed'].includes(appointment.status) && (
                      <Button size="sm" variant="outline" className="h-7 px-3 text-xs text-amber-700 border-amber-300 hover:bg-amber-50" onClick={() => handleNoShow(appointment.id)}>
                        No Show
                      </Button>
                    )}
                    {!['cancelled', 'completed', 'no_show'].includes(appointment.status) && (
                      <Button size="sm" variant="outline" className="h-7 px-3 text-xs text-red-600 border-red-200 hover:bg-red-50" onClick={() => openCancelDialog(appointment.id)}>
                        Cancel
                      </Button>
                    )}

                    {/* Divider */}
                    <div className="w-px h-4 bg-gray-300 mx-1 hidden md:block" />

                    {/* Document actions */}
                    <Button size="sm" variant="ghost" className="h-7 px-3 text-xs text-gray-600 hover:text-gray-900" onClick={() => openNotesDialog(appointment)}>
                      Notes
                    </Button>
                    {appointment.consultation_fee > 0 && (
                      <Button size="sm" variant="ghost" className="h-7 px-3 text-xs text-gray-600 hover:text-gray-900" onClick={() => showBillPreview(appointment.id)}>
                        View Bill
                      </Button>
                    )}
                    {appointment.patient_uuid && appointment.doctor_id && !['cancelled', 'no_show'].includes(appointment.status) && (
                      <Button size="sm" variant="ghost" className="h-7 px-3 text-xs text-indigo-600 hover:text-indigo-800" onClick={() => printBlankPrescription(appointment)}>
                        Blank Rx
                      </Button>
                    )}
                    {['completed', 'in_progress'].includes(appointment.status) && appointment.patient_uuid && (
                      <Button size="sm" variant="ghost" className="h-7 px-3 text-xs text-purple-600 hover:text-purple-800" onClick={() => showPrescriptionPreview(appointment.id, appointment.patient_uuid)}>
                        Prescription
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" className="h-7 px-3 text-xs text-teal-600 hover:text-teal-800" onClick={() => openLabPaymentDialog(appointment.patient_id)}>
                      Lab Orders
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Schedule Appointment Dialog */}
      <Dialog open={showAppointmentDialog} onOpenChange={setShowAppointmentDialog}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Schedule New Appointment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <PatientSearchPicker
              value={selectedPatient}
              onChange={handlePatientSelected}
              label="Search Patient (Name, Phone, or ID)"
              placeholder="Type patient name, phone number, or ID..."
              required
            />

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="doctor_id">Doctor *</Label>
                <Select value={appointmentForm.doctor_id} onValueChange={(value) => {
                  setAppointmentForm({...appointmentForm, doctor_id: value});
                  fetchAvailableSlots(value, appointmentForm.appointment_date);
                }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select Doctor" />
                  </SelectTrigger>
                  <SelectContent>
                    {doctors.map((doctor) => (
                      <SelectItem key={doctor.id} value={doctor.id.toString()}>
                        Dr. {doctor.first_name} {doctor.last_name} - {doctor.specialization || 'General'}
                        {doctor.consultation_fee_inr && (
                          <span className="text-sm text-gray-500 ml-2">
                            ({doctor.consultation_fee_inr})
                          </span>
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label htmlFor="appointment_date">Date *</Label>
                <Input
                  id="appointment_date"
                  type="date"
                  value={appointmentForm.appointment_date}
                  onChange={(e) => {
                    setAppointmentForm({...appointmentForm, appointment_date: e.target.value});
                    if (appointmentForm.doctor_id) {
                      fetchAvailableSlots(appointmentForm.doctor_id, e.target.value);
                    }
                  }}
                  min={localDateString()}
                  required
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

              <AppointmentAvailabilityOverride
                className="md:col-span-2"
                overrideAvailability={appointmentForm.override_availability}
                overrideReason={appointmentForm.override_reason}
                onChange={(patch) => setAppointmentForm({ ...appointmentForm, ...patch })}
              />

              <div>
                <Label htmlFor="appointment_type">Type</Label>
                <Select value={appointmentForm.appointment_type} onValueChange={(value) => setAppointmentForm({...appointmentForm, appointment_type: value})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="consultation">Consultation</SelectItem>
                    <SelectItem value="followup">Follow-up</SelectItem>
                    <SelectItem value="checkup">Check-up</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="payment_method">Payment Method</Label>
                <Select value={appointmentForm.payment_method} onValueChange={(value) => setAppointmentForm({...appointmentForm, payment_method: value})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="insurance">Insurance</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Fee Summary */}
            {selectedPatient && appointmentForm.doctor_id && (
              <div className="bg-gray-50 rounded-lg p-4 border">
                <h4 className="font-medium mb-2">Fee Summary</h4>
                <div className="space-y-1 text-sm">
                  {(() => {
                    const doctor = doctors.find(d => d.id.toString() === appointmentForm.doctor_id.toString());
                    const isFollowup = appointmentForm.appointment_type === 'followup';
                    const baseFee = doctor?.consultation_fee_inr
                      ? parseFloat(doctor.consultation_fee_inr.replace('₹', '').replace(',', '').trim()) || 0
                      : 0;
                    const consultFee = isFollowup ? 0 : baseFee;
                    const regFee = patientFeeInfo.is_new_patient ? patientFeeInfo.registration_fee : 0;
                    const total = consultFee + regFee - (parseFloat(appointmentForm.discount_amount) || 0);
                    return (
                      <>
                        <div className="flex justify-between">
                          <span>Consultation Fee{isFollowup ? ' (Follow-up — free)' : ''}</span>
                          <span>₹{consultFee.toFixed(2)}</span>
                        </div>
                        {patientFeeInfo.is_new_patient && regFee > 0 && (
                          <div className="flex justify-between text-blue-600">
                            <span>Registration Fee (New Patient)</span>
                            <span>₹{regFee.toFixed(2)}</span>
                          </div>
                        )}
                        {patientFeeInfo.is_new_patient && regFee === 0 && (
                          <div className="flex justify-between text-gray-400">
                            <span>Registration Fee (Not set)</span>
                            <span>₹0.00</span>
                          </div>
                        )}
                        <div className="flex items-center justify-between">
                          <span>Discount</span>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-400">₹</span>
                            <Input
                              type="number"
                              min="0"
                              step="0.01"
                              value={appointmentForm.discount_amount || ''}
                              onChange={(e) => setAppointmentForm({...appointmentForm, discount_amount: parseFloat(e.target.value) || 0})}
                              placeholder="0"
                              className="w-24 h-7 text-right text-sm"
                            />
                          </div>
                        </div>
                        <hr className="my-1" />
                        <div className="flex justify-between font-semibold text-base">
                          <span>Total</span>
                          <span>₹{total.toFixed(2)}</span>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            <div>
              <Label htmlFor="reason">Reason for Visit</Label>
              <Input
                id="reason"
                value={appointmentForm.reason}
                onChange={(e) => setAppointmentForm({...appointmentForm, reason: e.target.value})}
                placeholder="Brief description of the visit reason"
              />
            </div>

            <ReferralSelectWithCreate
              value={appointmentForm.referred_by}
              onValueChange={(name) => setAppointmentForm({ ...appointmentForm, referred_by: name })}
              referrals={referralList}
              onReferralsChange={setReferralList}
            />

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowAppointmentDialog(false)} className="flex-1">
                Cancel
              </Button>
              <Button
                onClick={createAppointment}
                disabled={isAppointmentSubmitDisabled(appointmentForm, { loading, selectedPatient: !!selectedPatient })}
                className="flex-1"
              >
                {loading ? 'Booking...' : 'Book Appointment'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Cancel Appointment Dialog */}
      <Dialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel Appointment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Reason for Cancellation *</Label>
              <Textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Enter reason for cancellation..."
                rows={3}
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowCancelDialog(false)} className="flex-1">
                Go Back
              </Button>
              <Button variant="destructive" onClick={handleCancelAppointment} className="flex-1" disabled={!cancelReason.trim()}>
                Confirm Cancel
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reschedule Appointment Dialog */}
      <Dialog open={showRescheduleDialog} onOpenChange={setShowRescheduleDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reschedule Appointment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>New Date *</Label>
              <Input
                type="date"
                value={rescheduleForm.new_date}
                onChange={(e) => {
                  setRescheduleForm({ ...rescheduleForm, new_date: e.target.value, new_time: '' });
                  fetchRescheduleSlots(rescheduleDoctor, e.target.value);
                }}
                min={localDateString()}
              />
            </div>
            <div>
              <Label>New Time *</Label>
              {rescheduleSlots.length > 0 ? (
                <Select value={rescheduleForm.new_time} onValueChange={(value) => setRescheduleForm({ ...rescheduleForm, new_time: value })}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select Available Time" />
                  </SelectTrigger>
                  <SelectContent>
                    {rescheduleSlots.map((slot, index) => (
                      <SelectItem key={index} value={slot.start_time}>
                        {slot.start_time} - {slot.end_time}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  type="time"
                  value={rescheduleForm.new_time}
                  onChange={(e) => setRescheduleForm({ ...rescheduleForm, new_time: e.target.value })}
                />
              )}
              {rescheduleForm.new_date && rescheduleSlots.length === 0 && (
                <p className="text-sm text-red-600 mt-1">No available slots for selected date</p>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowRescheduleDialog(false)} className="flex-1">
                Cancel
              </Button>
              <Button onClick={handleReschedule} className="flex-1" disabled={!rescheduleForm.new_date || !rescheduleForm.new_time}>
                Confirm Reschedule
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Notes Dialog */}
      <Dialog open={showNotesDialog} onOpenChange={setShowNotesDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Appointment Notes</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              placeholder="Enter notes..."
              rows={5}
            />
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowNotesDialog(false)} className="flex-1">
                Cancel
              </Button>
              <Button onClick={handleSaveNotes} className="flex-1">
                Save Notes
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prescription Preview Dialog */}
      <Dialog open={showPrescriptionDialog} onOpenChange={closePrescriptionPreview}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Prescription - {prescriptionData?.prescription_id}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4 h-full">
            {prescriptionData && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-600">Patient</p>
                  <p className="font-semibold">{prescriptionData.patient_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Doctor</p>
                  <p className="font-semibold">{prescriptionData.doctor_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Date</p>
                  <p className="font-semibold">{new Date(prescriptionData.prescription_date).toLocaleDateString()}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Medicines</p>
                  <p className="font-semibold">{prescriptionData.medicines?.length || 0} items</p>
                </div>
              </div>
            )}
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {prescriptionPdfUrl && (
                <iframe src={prescriptionPdfUrl} className="w-full h-full border-0" title="Prescription Preview" />
              )}
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={closePrescriptionPreview}>Close</Button>
              <Button onClick={printPrescription} className="bg-purple-600 hover:bg-purple-700">
                <Printer className="h-4 w-4 mr-2" />
                Print
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Lab Payment Dialog */}
      <Dialog open={showLabPaymentDialog} onOpenChange={setShowLabPaymentDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube className="h-5 w-5" />
              Lab Order Payments
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {labPaymentLoading ? (
              <div className="text-center py-8 text-gray-500">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                Loading pending orders...
              </div>
            ) : allLabOrders.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <TestTube className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                <p>No lab orders for this patient.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Pending Payment Orders */}
                {pendingLabOrders.length > 0 && (
                  <>
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-700">Pending Payment ({pendingLabOrders.length})</p>
                      <p className="font-semibold text-green-700">
                        Total: ₹{pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0).toFixed(2)}
                      </p>
                    </div>

                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {(() => {
                        const groups = [];
                        const pkgMap = {};
                        for (const order of pendingLabOrders) {
                          if (order.package_booking_id) {
                            if (!pkgMap[order.package_booking_id]) {
                              pkgMap[order.package_booking_id] = { name: order.package_name || 'Package', orders: [] };
                              groups.push({ type: 'package', key: order.package_booking_id, data: pkgMap[order.package_booking_id] });
                            }
                            pkgMap[order.package_booking_id].orders.push(order);
                          } else {
                            groups.push({ type: 'single', key: order.id, data: order });
                          }
                        }
                        return groups.map(g => {
                          if (g.type === 'package') {
                            const pkg = g.data;
                            return (
                              <div key={g.key} className="bg-indigo-50/50 border-l-4 border-indigo-400">
                                <div className="flex items-center gap-2 px-3 pt-2 pb-1">
                                  <Package className="h-3.5 w-3.5 text-indigo-600" />
                                  <span className="font-semibold text-xs text-indigo-700">{pkg.name}</span>
                                  <span className="text-xs text-indigo-500">({pkg.orders.length} tests)</span>
                                  <span className="ml-auto font-semibold text-sm">₹{pkg.orders.reduce((s, o) => s + (o.amount || 0), 0).toFixed(2)}</span>
                                </div>
                                {pkg.orders.map(order => (
                                  <div key={order.id} className="px-3 py-1.5 pl-8 flex items-center justify-between">
                                    <div>
                                      <p className="text-sm">{order.test_name}</p>
                                      <p className="text-xs text-gray-400">#{order.order_number} | {order.test_code}</p>
                                    </div>
                                    <p className="text-xs text-gray-500">₹{(order.amount || 0).toFixed(2)}</p>
                                  </div>
                                ))}
                              </div>
                            );
                          }
                          const order = g.data;
                          return (
                            <div key={order.id} className="p-3 flex items-center justify-between">
                              <div>
                                <p className="font-medium text-sm">{order.test_name}</p>
                                <p className="text-xs text-gray-500">{order.order_number} | {order.test_code} | Dr. {order.doctor_name?.replace('Dr. ', '')}</p>
                                {order.priority !== 'normal' && <Badge variant="destructive" className="text-xs mt-0.5">{order.priority}</Badge>}
                              </div>
                              <p className="font-semibold text-sm">₹{(order.amount || 0).toFixed(2)}</p>
                            </div>
                          );
                        });
                      })()}
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <Label className="text-xs">Payment Method</Label>
                        <Select value={labPaymentMethod} onValueChange={setLabPaymentMethod}>
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="cash">Cash</SelectItem>
                            <SelectItem value="card">Card</SelectItem>
                            <SelectItem value="upi">UPI</SelectItem>
                            <SelectItem value="online">Online</SelectItem>
                            <SelectItem value="insurance">Insurance</SelectItem>
                            <SelectItem value="cheque">Cheque</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Button className="mt-4" onClick={collectAllLabPayments} disabled={labPaymentLoading}>
                        {labPaymentLoading ? 'Generating Bill...' : `Pay & Download Bill (₹${pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0).toFixed(2)})`}
                      </Button>
                    </div>
                  </>
                )}

                {/* Paid, in progress */}
                {labInProgressOrders.length > 0 && (
                  <>
                    {(pendingLabOrders.length > 0) && <hr className="my-2" />}
                    <p className="text-sm font-medium text-gray-700">
                      In Progress ({labInProgressOrders.length})
                    </p>
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {labInProgressOrders.map((order) => (
                        <div key={order.id} className="p-3 flex items-center justify-between">
                          <div>
                            <p className="font-medium text-sm">{order.test_name}</p>
                            <p className="text-xs text-gray-500">
                              {order.order_number} | {order.test_code} | Dr. {order.doctor_name?.replace('Dr. ', '')}
                            </p>
                          </div>
                          <Badge variant="secondary" className="text-xs capitalize">{order.status}</Badge>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* Completed Reports - Download */}
                {labReportOrders.length > 0 && (
                  <>
                    {(pendingLabOrders.length > 0 || labInProgressOrders.length > 0) && <hr className="my-2" />}
                    <p className="text-sm font-medium text-gray-700">Completed Reports</p>
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {(() => {
                        const reportOrders = labReportOrders;
                        const groups = [];
                        const pkgMap = {};
                        for (const order of reportOrders) {
                          if (order.package_booking_id) {
                            if (!pkgMap[order.package_booking_id]) {
                              pkgMap[order.package_booking_id] = { name: order.package_name || 'Package', orders: [] };
                              groups.push({ type: 'package', key: order.package_booking_id, data: pkgMap[order.package_booking_id] });
                            }
                            pkgMap[order.package_booking_id].orders.push(order);
                          } else {
                            groups.push({ type: 'single', key: order.id, data: order });
                          }
                        }
                        return groups.map(g => {
                          if (g.type === 'package') {
                            const pkg = g.data;
                            return (
                              <div key={g.key} className="bg-indigo-50/50 border-l-4 border-indigo-400">
                                <div className="flex items-center gap-2 px-3 pt-2 pb-1">
                                  <Package className="h-3.5 w-3.5 text-indigo-600" />
                                  <span className="font-semibold text-xs text-indigo-700">{pkg.name}</span>
                                  <span className="text-xs text-indigo-500">({pkg.orders.length} tests)</span>
                                </div>
                                {pkg.orders.map(order => (
                                  <div key={order.id} className="px-3 py-1.5 pl-8 flex items-center justify-between">
                                    <div>
                                      <p className="text-sm">{order.test_name}</p>
                                      <p className="text-xs text-gray-400">#{order.order_number} | {order.test_code}</p>
                                    </div>
                                    <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={() => downloadLabReport(order.report_id, order.order_number)}>
                                      <Printer className="h-3 w-3 mr-1" />Download
                                    </Button>
                                  </div>
                                ))}
                                <div className="px-3 py-2 border-t border-indigo-200">
                                  <Button size="sm" variant="outline" className="h-6 px-2 text-xs border-indigo-300 text-indigo-700"
                                    onClick={() => downloadLabReport(null, pkg.name, g.key)}>
                                    <Printer className="h-3 w-3 mr-1" />All Reports
                                  </Button>
                                </div>
                              </div>
                            );
                          }
                          const order = g.data;
                          return (
                            <div key={order.id} className="p-3 flex items-center justify-between">
                              <div>
                                <p className="font-medium text-sm">{order.test_name}</p>
                                <p className="text-xs text-gray-500">{order.order_number} | {order.test_code}</p>
                              </div>
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => downloadLabReport(order.report_id, order.order_number)}>
                                <Printer className="h-3 w-3 mr-1" />Download
                              </Button>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Bill Preview Dialog */}
      <Dialog open={showBillPreviewDialog} onOpenChange={closeBillPreview}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" />
              Bill Preview - {currentBill?.bill_number}
            </DialogTitle>
          </DialogHeader>

          <div className="flex flex-col space-y-4 h-full">
            {/* Bill Summary */}
            {currentBill && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-600">Patient</p>
                  <p className="font-semibold">{currentBill.patient_name}</p>
                  {(currentBill.patient_age_display || currentBill.patient_gender) && (
                    <p className="text-xs text-gray-500">
                      {[currentBill.patient_age_display, currentBill.patient_gender].filter(Boolean).join(' · ')}
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-sm text-gray-600">Doctor</p>
                  <p className="font-semibold">{currentBill.doctor_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Total Amount</p>
                  <p className="font-semibold text-green-600">₹{currentBill.total_amount?.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Payment Status</p>
                  <Badge variant={currentBill.balance_due === 0 ? "success" : "secondary"}>
                    {currentBill.balance_due === 0 ? "Paid" : "Pending"}
                  </Badge>
                </div>
              </div>
            )}

            {/* PDF Preview */}
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {billPdfUrl && (
                <iframe
                  src={billPdfUrl}
                  className="w-full h-full border-0"
                  title="Bill Preview"
                />
              )}
            </div>

            {/* Action Buttons */}
            <p className="text-xs text-muted-foreground pt-2">
              Letterhead follows Settings → Print Settings.
            </p>
            <div className="flex items-center gap-3 pt-2">
              <Button variant="outline" onClick={closeBillPreview} className="flex-1">
                Close
              </Button>
              <Button onClick={printBill} className="flex-1 bg-blue-600 hover:bg-blue-700">
                <Printer className="h-4 w-4 mr-2" />
                Print Bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState(prev => ({ ...prev, open }))}
        title={confirmState.title}
        description={confirmState.description}
        onConfirm={confirmState.onConfirm}
      />

      {/* Lab Bill Preview Dialog */}
      <Dialog open={showLabBillPreview} onOpenChange={() => {
        if (labBillPdfUrl) { window.URL.revokeObjectURL(labBillPdfUrl); setLabBillPdfUrl(null); }
        setShowLabBillPreview(false);
      }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" /> Lab Bill Preview
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4">
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {labBillPdfUrl && (
                <iframe src={labBillPdfUrl} className="w-full h-full min-h-[400px] border-0" title="Lab Bill Preview" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button variant="outline" onClick={() => {
                if (labBillPdfUrl) { window.URL.revokeObjectURL(labBillPdfUrl); setLabBillPdfUrl(null); }
                setShowLabBillPreview(false);
              }} className="flex-1">Close</Button>
              <Button onClick={() => {
                if (labBillPdfUrl) {
                  const iframe = document.createElement('iframe');
                  iframe.style.display = 'none';
                  document.body.appendChild(iframe);
                  iframe.src = labBillPdfUrl;
                  iframe.onload = () => {
                    iframe.contentWindow.print();
                    setTimeout(() => document.body.removeChild(iframe), 1000);
                  };
                }
              }} className="flex-1 bg-blue-600 hover:bg-blue-700">
                <Printer className="h-4 w-4 mr-2" /> Print Bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Blank Rx is available from each appointment row only — not after booking */}
    </div>
  );
};

export default ReceptionAppointmentsPage;