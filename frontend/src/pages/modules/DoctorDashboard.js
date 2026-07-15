import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import {
  Calendar, Clock, User, FileText, TestTube, Pill, CheckCircle, XCircle,
  Activity, Info, Printer, RefreshCw, Eye, Hash,
  History, Stethoscope, AlertCircle, ChevronRight, ChevronDown, Bed, Plus, ClipboardList
} from 'lucide-react';
import axios from 'axios';
import { format } from 'date-fns';
import VitalsForm from '../../components/vitals/VitalsForm';
import MedicineLookupInput from '../../components/inpatient/MedicineLookupInput';
import PrescriptionScheduleFields from '../../components/prescription/PrescriptionScheduleFields';
import { BLANK_INPATIENT_RX_ITEM } from '../../utils/prescriptionSchedule';
import { useToast } from '../../hooks/use-toast';
import { printPdfFromUrl } from '../../utils/printPdf';
import DischargeSummaryEditor from './inpatient/DischargeSummaryEditor';
import DischargeSummaryPreviewCard from './inpatient/discharge/DischargeSummaryPreviewCard';
import { DISCHARGE_SUMMARY_STATUS } from './inpatient/discharge/constants';
import { enrichAdmissionsWithSummaryStatus, prepareDischargeSummaryEdit, summaryIsReadyForPrint } from './inpatient/discharge/dischargeSummaryUtils';

const isMyInpatientAdmission = (adm, userId) => (
  adm.admitting_doctor_id === userId || adm.attending_physician_id === userId
);

const DoctorDashboard = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [user, setUser] = useState(null);
  const [appointments, setAppointments] = useState([]);
  const [completedAppointments, setCompletedAppointments] = useState([]);
  const [showCompletedAppointments, setShowCompletedAppointments] = useState(false);
  const [selectedAppointment, setSelectedAppointment] = useState(null);
  const [prescriptions, setPrescriptions] = useState([]);
  const [showPrescriptionDialog, setShowPrescriptionDialog] = useState(false);
  const [showLabOrderDialog, setShowLabOrderDialog] = useState(false);
  const [labDuplicateWarning, setLabDuplicateWarning] = useState(null);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const [showPrintPreviewDialog, setShowPrintPreviewDialog] = useState(false);
  const [activeTab, setActiveTab] = useState('appointments');
  const [loading, setLoading] = useState(false);

  // Inpatient state
  const [inpatientEnabled, setInpatientEnabled] = useState(false);
  const [doctorAdmissions, setDoctorAdmissions] = useState([]);
  const [doctorDischargedAdmissions, setDoctorDischargedAdmissions] = useState([]);
  const [inpatientListTab, setInpatientListTab] = useState('active');
  const [showDoctorVisitDialog, setShowDoctorVisitDialog] = useState(false);
  const [doctorVisitAdmission, setDoctorVisitAdmission] = useState(null);
  const [doctorVisitNotes, setDoctorVisitNotes] = useState('');
  const [wardRoundAdmission, setWardRoundAdmission] = useState(null);
  const [wardRoundVisits, setWardRoundVisits] = useState([]);
  const [wardRoundNursingNotes, setWardRoundNursingNotes] = useState([]);
  const [wardRoundVitals, setWardRoundVitals] = useState([]);
  const [wardRoundPrescriptions, setWardRoundPrescriptions] = useState([]);
  const [wardRoundLabOrders, setWardRoundLabOrders] = useState([]);
  const [wardRoundAllergies, setWardRoundAllergies] = useState([]);
  const [wardRoundSummary, setWardRoundSummary] = useState(null);
  const [wardRoundTab, setWardRoundTab] = useState('overview');
  const [showManageAdmissionDialog, setShowManageAdmissionDialog] = useState(false);
  // Inpatient-specific Add Prescription dialog
  const RX_BLANK_ITEM = BLANK_INPATIENT_RX_ITEM;
  const [showInpatientRxDialog, setShowInpatientRxDialog] = useState(false);
  const [inpatientRxForm, setInpatientRxForm] = useState({ notes: '', items: [{ ...RX_BLANK_ITEM }] });
  // Inpatient-specific Order Lab dialog
  const [showInpatientLabDialog, setShowInpatientLabDialog] = useState(false);
  const [inpatientLabForm, setInpatientLabForm] = useState({ test_ids: [], priority: 'normal', notes: '' });
  const [inpatientLabAvailableTests, setInpatientLabAvailableTests] = useState([]);
  const [inpatientLabSearch, setInpatientLabSearch] = useState('');
  const [showDischargeSummaryEditor, setShowDischargeSummaryEditor] = useState(false);
  const [inpatientDoctorsList, setInpatientDoctorsList] = useState([]);

  // Preview state
  const [previewPrescription, setPreviewPrescription] = useState(null);
  const [previewPdfUrl, setPreviewPdfUrl] = useState(null);

  // Success feedback state
  const [successMessage, setSuccessMessage] = useState('');
  const [showSuccessDialog, setShowSuccessDialog] = useState(false);
  const [createdPrescription, setCreatedPrescription] = useState(null);

  // Consultation dialog state
  const [showConsultationDialog, setShowConsultationDialog] = useState(false);
  const [consultationForm, setConsultationForm] = useState({
    chief_complaint: '',
    present_history: '',
    examination_findings: '',
    notes: '',
    follow_up_date: ''
  });
  const [activeConsultation, setActiveConsultation] = useState(null);

  // Patient history dialog state
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [patientHistory, setPatientHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Notes dialog state
  const [showNotesDialog, setShowNotesDialog] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [notesAppointment, setNotesAppointment] = useState(null);

  // Queue state
  const [queueData, setQueueData] = useState(null);

  // Auto-refresh
  const [lastRefreshed, setLastRefreshed] = useState(new Date());

  // Prescription form state
  const [prescriptionForm, setPrescriptionForm] = useState({
    medications: [{
      medicine_id: '',
      medicine_name: '',
      quantity_prescribed: 1,
      dosage: '',
      frequency_schedule: '1-0-0',
      food_timing: 'after_food',
      duration: '',
      instructions: ''
    }],
    diagnosis: '',
    notes: '',
    follow_up_date: ''
  });

  // Lab order form state
  const [availableLabTests, setAvailableLabTests] = useState([]);
  const [labCategories, setLabCategories] = useState([]);
  const [selectedLabTests, setSelectedLabTests] = useState([]);
  const [labOrderPriority, setLabOrderPriority] = useState('normal');
  const [labOrderNotes, setLabOrderNotes] = useState('');
  const [labSearchQuery, setLabSearchQuery] = useState('');
  const [labCategoryFilter, setLabCategoryFilter] = useState('all');
  const [labOrderSubmitting, setLabOrderSubmitting] = useState(false);

  const [customLabTests, setCustomLabTests] = useState([]);
  const [customLabTestInput, setCustomLabTestInput] = useState('');

  // Lab results state
  const [labOrders, setLabOrders] = useState([]);
  const [labReports, setLabReports] = useState([]);
  const [showLabReportDialog, setShowLabReportDialog] = useState(false);
  const [viewingLabReport, setViewingLabReport] = useState(null);
  const [expandedRxGroups, setExpandedRxGroups] = useState({});
  const [expandedLabGroups, setExpandedLabGroups] = useState({});

  // --- Time formatting helper ---
  const formatTime = (timeStr) => {
    if (!timeStr) return '';
    const parts = timeStr.split(':');
    let hours = parseInt(parts[0], 10);
    const minutes = parts[1];
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    return `${hours}:${minutes} ${ampm}`;
  };

  // --- Data fetching ---
  useEffect(() => {
    fetchUserProfile();
  }, []);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (user) {
        fetchTodayAppointments(user.id);
        fetchQueueData(user.id);
        setLastRefreshed(new Date());
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [user]);

  const loadDoctorDischargedAdmissions = async (userData) => {
    try {
      const r = await axios.get('/api/inpatient/admissions', { params: { status: 'discharged', limit: 100 } });
      const list = r.data?.items || (Array.isArray(r.data) ? r.data : []);
      const mine = list.filter(a => isMyInpatientAdmission(a, userData.id));
      const enriched = await enrichAdmissionsWithSummaryStatus(mine);
      setDoctorDischargedAdmissions(enriched);
    } catch {
      setDoctorDischargedAdmissions([]);
    }
  };

  const fetchUserProfile = async () => {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const userData = JSON.parse(userStr);
        setUser(userData);
        fetchTodayAppointments(userData.id);
        fetchPrescriptions();
        fetchQueueData(userData.id);
        fetchAvailableLabTests();
        fetchLabOrders();
        // Check inpatient module
        axios.get('/api/system/enabled-modules').then(res => {
          const mod = (res.data || []).find(m => m.module_name === 'inpatient');
          if (mod?.is_enabled) {
            setInpatientEnabled(true);
            axios.get('/api/inpatient/doctors')
              .then(r => setInpatientDoctorsList(r.data || []))
              .catch(() => {});
            axios.get('/api/inpatient/admissions', { params: { status: 'admitted' } })
              .then(r => {
                const list = r.data?.items || (Array.isArray(r.data) ? r.data : []);
                setDoctorAdmissions(list.filter(a => isMyInpatientAdmission(a, userData.id)));
              }).catch(() => {});
            loadDoctorDischargedAdmissions(userData);
          }
        }).catch(() => {});
      }
    } catch (error) {
      console.error('Error fetching user profile:', error);
    }
  };

  // ============================================================
  // Inpatient ward-rounds: comprehensive admission view
  // ============================================================
  const openManageAdmission = async (adm) => {
    setWardRoundAdmission(adm);
    setWardRoundTab('overview');
    setShowManageAdmissionDialog(true);
    // Reset and refetch every section
    setWardRoundVisits([]); setWardRoundNursingNotes([]); setWardRoundVitals([]);
    setWardRoundPrescriptions([]); setWardRoundLabOrders([]);     setWardRoundAllergies([]);
    setWardRoundSummary(null);
    const opts = (p) => axios.get(p).then(r => r.data).catch(() => null);
    const [v, nn, vit, rx, lo, al, sum] = await Promise.all([
      opts(`/api/inpatient/admissions/${adm.id}/visits`),
      opts(`/api/inpatient/admissions/${adm.id}/nursing-notes`),
      opts(`/api/inpatient/admissions/${adm.id}/vitals?limit=20`),
      opts(`/api/inpatient/admissions/${adm.id}/prescriptions`),
      opts(`/api/inpatient/admissions/${adm.id}/lab-orders`),
      adm.patient_id ? opts(`/api/patients/${adm.patient_id}/allergies?active_only=true`) : Promise.resolve(null),
      opts(`/api/inpatient/admissions/${adm.id}/discharge-summary`),
    ]);
    if (Array.isArray(v)) setWardRoundVisits(v);
    if (Array.isArray(nn)) setWardRoundNursingNotes(nn);
    if (Array.isArray(vit)) setWardRoundVitals(vit);
    if (Array.isArray(rx)) setWardRoundPrescriptions(rx);
    if (Array.isArray(lo)) setWardRoundLabOrders(lo);
    if (Array.isArray(al)) setWardRoundAllergies(al);
    setWardRoundSummary(sum || null);
  };

  /** Open discharge summary editor only (reception completes checkout separately). */
  const openDischargeSummary = async (adm, e) => {
    e?.stopPropagation?.();
    setWardRoundAdmission(adm);
    try {
      const updated = await prepareDischargeSummaryEdit(adm.id);
      if (updated) setWardRoundSummary(updated);
      setShowDischargeSummaryEditor(true);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Could not open summary',
        description: typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail : 'Network error',
      });
    }
  };

  const openDischargeSummaryEditor = async () => {
    if (!wardRoundAdmission) return;
    try {
      const updated = await prepareDischargeSummaryEdit(wardRoundAdmission.id);
      if (updated) setWardRoundSummary(updated);
      setShowDischargeSummaryEditor(true);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Could not open summary',
        description: typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail : 'Network error',
      });
    }
  };

  const wardRoundSummaryStatus = wardRoundSummary?.status || null;
  const summaryReadyForPrint = wardRoundSummaryStatus === 'ready' || wardRoundSummaryStatus === 'locked';
  const wardRoundIsDischarged = wardRoundAdmission?.status === 'discharged';

  const printWardRoundDischargeSummary = async () => {
    if (!wardRoundAdmission) return;
    const ok = await printPdfFromUrl(`/api/inpatient/admissions/${wardRoundAdmission.id}/discharge-summary/pdf`);
    if (!ok) {
      toast({
        variant: 'destructive',
        title: 'Print failed',
        description: 'Mark the discharge summary ready for print first.',
      });
    }
  };

  const printWardRoundAdmissionDetail = async () => {
    if (!wardRoundAdmission) return;
    await printPdfFromUrl(`/api/inpatient/admissions/${wardRoundAdmission.id}/admission-detail/pdf`);
  };

  const refreshManageAdmission = async () => {
    if (wardRoundAdmission) await openManageAdmission(wardRoundAdmission);
  };

  const handleInpatientRxSubmit = async (e) => {
    e.preventDefault();
    const items = inpatientRxForm.items
      .map(it => ({
        medicine_id: it.medicine_id ? parseInt(it.medicine_id) : null,
        medicine_name: it.medicine_id ? null : (it.medicine_name?.trim() || null),
        quantity_prescribed: Math.max(1, parseInt(it.quantity_prescribed) || 1),
        dosage: it.dosage?.trim() || '',
        duration: it.duration?.trim() || '',
        frequency_schedule: it.frequency_schedule || '1-0-0',
        food_timing: it.food_timing || 'after_food',
        instructions: it.instructions?.trim() || null,
      }))
      .filter(it => (it.medicine_id || it.medicine_name) && it.dosage && it.duration);
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Error', description: 'Add at least one medicine with dosage and duration' });
      return;
    }
    try {
      await axios.post('/api/prescriptions/', {
        patient_id: wardRoundAdmission.patient_id,
        admission_id: wardRoundAdmission.id,
        notes: inpatientRxForm.notes || null,
        items,
      });
      toast({ title: 'Prescription created' });
      setShowInpatientRxDialog(false);
      setInpatientRxForm({ notes: '', items: [{ ...RX_BLANK_ITEM }] });
      refreshManageAdmission();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create prescription';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const openInpatientLabDialog = async () => {
    if (!wardRoundAdmission) return;
    setInpatientLabForm({ test_ids: [], priority: 'normal', notes: '' });
    setInpatientLabSearch('');
    try {
      const r = await axios.get(`/api/inpatient/admissions/${wardRoundAdmission.id}/lab-tests-available`);
      setInpatientLabAvailableTests(r.data || []);
    } catch { setInpatientLabAvailableTests([]); }
    setShowInpatientLabDialog(true);
  };

  const handleInpatientLabSubmit = async (e) => {
    e.preventDefault();
    if (!inpatientLabForm.test_ids.length) {
      toast({ variant: 'destructive', title: 'Error', description: 'Select at least one lab test' });
      return;
    }
    try {
      await axios.post('/api/lab/orders', {
        patient_id: wardRoundAdmission.patient_id,
        admission_id: wardRoundAdmission.id,
        test_ids: inpatientLabForm.test_ids,
        priority: inpatientLabForm.priority,
        notes: inpatientLabForm.notes || null,
        force: false,
      });
      toast({ title: 'Lab order created' });
      setShowInpatientLabDialog(false);
      refreshManageAdmission();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Failed to create lab order');
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const fetchTodayAppointments = async (doctorId = null) => {
    try {
      const token = localStorage.getItem('token');
      const today = format(new Date(), 'yyyy-MM-dd');

      let url;
      if (doctorId) {
        url = `/api/appointments/doctor/${doctorId}?date_from=${today}&date_to=${today}`;
      } else {
        url = `/api/appointments/?date_from=${today}&date_to=${today}`;
      }

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        if (doctorId) {
          setAppointments(data);
        } else {
          const userData = user || JSON.parse(localStorage.getItem('user') || '{}');
          setAppointments(data.filter(apt => apt.doctor_id === userData.id));
        }
      }
    } catch (error) {
      console.error('Error fetching appointments:', error);
    }
  };

  const fetchCompletedAppointments = async (doctorId = null) => {
    try {
      const token = localStorage.getItem('token');
      const today = format(new Date(), 'yyyy-MM-dd');
      const thirtyDaysAgo = format(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), 'yyyy-MM-dd');

      let url;
      if (doctorId) {
        url = `/api/appointments/doctor/${doctorId}?date_from=${thirtyDaysAgo}&date_to=${today}`;
      } else {
        url = `/api/appointments/?date_from=${thirtyDaysAgo}&date_to=${today}`;
      }

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setCompletedAppointments(data.filter(apt => apt.status === 'completed'));
      }
    } catch (error) {
      console.error('Error fetching completed appointments:', error);
    }
  };

  const fetchPrescriptions = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/prescriptions-simple/', {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setPrescriptions(data);
      }
    } catch (error) {
      console.error('Error fetching prescriptions:', error);
    }
  };

  const fetchQueueData = async (doctorId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/queue/${doctorId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setQueueData(data);
      }
    } catch (error) {
      console.error('Error fetching queue:', error);
    }
  };

  const queueAction = async (action, appointmentId) => {
    const doctorId = user?.id;
    if (!doctorId) return;
    try {
      const token = localStorage.getItem('token');
      const url = appointmentId
        ? `/api/appointments/queue/${doctorId}/${action}/${appointmentId}`
        : `/api/appointments/queue/${doctorId}/${action}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const msg = typeof data.detail === 'string' ? data.detail : `Failed to ${action}`;
        toast({ title: 'Error', description: msg, variant: 'destructive' });
        return;
      }
      toast({ title: 'Queue updated', description: data.message || `${action} complete` });
      await fetchQueueData(doctorId);
      await fetchTodayAppointments(doctorId);
    } catch (error) {
      console.error(`Queue ${action} error:`, error);
      toast({ title: 'Error', description: `Failed to ${action}`, variant: 'destructive' });
    }
  };

  // --- Patient history ---
  const fetchPatientHistory = async (appointment) => {
    setHistoryLoading(true);
    setShowHistoryDialog(true);
    try {
      const token = localStorage.getItem('token');
      // First get patient UUID from search
      const searchResponse = await fetch('/api/patients/search', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_term: appointment.patient_name.split(' ')[0],
          sort_by: 'name',
          sort_order: 'asc'
        })
      });

      if (searchResponse.ok) {
        const searchData = await searchResponse.json();
        const patient = searchData.patients?.find(p =>
          `${p.first_name} ${p.last_name}` === appointment.patient_name
        );

        if (patient) {
          const historyResponse = await fetch(`/api/appointments/patient/${patient.patient_id}/history`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          if (historyResponse.ok) {
            setPatientHistory(await historyResponse.json());
          }
        }
      }
    } catch (error) {
      console.error('Error fetching patient history:', error);
    } finally {
      setHistoryLoading(false);
    }
  };

  // --- Appointment notes ---
  const openNotesDialog = (appointment) => {
    setNotesAppointment(appointment);
    setNotesText(appointment.notes || '');
    setShowNotesDialog(true);
  };

  const handleSaveNotes = async () => {
    if (!notesAppointment) return;
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${notesAppointment.id}/notes`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notesText })
      });
      if (response.ok) {
        setAppointments(prev =>
          prev.map(apt => apt.id === notesAppointment.id ? { ...apt, notes: notesText } : apt)
        );
        setShowNotesDialog(false);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to save notes' });
      }
    } catch (error) {
      console.error('Error saving notes:', error);
    }
  };

  // --- Consultation ---
  const openConsultationDialog = async (appointment) => {
    setSelectedAppointment(appointment);
    setConsultationForm({
      chief_complaint: appointment.reason || '',
      present_history: '',
      examination_findings: '',
      notes: '',
      follow_up_date: ''
    });
    setActiveConsultation(null);
    setCreatedPrescription(null);
    setShowConsultationDialog(true);

    // Try to load existing consultation for this appointment
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/consultations/by-appointment/${appointment.id}`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveConsultation(data);
        setConsultationForm({
          chief_complaint: data.chief_complaint || appointment.reason || '',
          present_history: data.present_history || '',
          examination_findings: data.examination_findings || '',
          notes: data.notes || '',
          follow_up_date: data.follow_up_date ? data.follow_up_date.split('T')[0] : ''
        });
        // Load existing prescription for this consultation or appointment (incl. blank Rx from reception)
        const rxRes = await fetch(`/api/prescriptions-simple/?consultation_id=${data.id}`, {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
        });
        if (rxRes.ok) {
          const rxData = await rxRes.json();
          if (rxData.length > 0) {
            setCreatedPrescription(rxData[0]);
          }
        }
      }
      const rxByAptRes = await fetch(`/api/prescriptions-simple/?appointment_id=${appointment.id}`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (rxByAptRes.ok) {
        const rxByApt = await rxByAptRes.json();
        if (rxByApt.length > 0) {
          setCreatedPrescription(rxByApt[0]);
        }
      }
    } catch (err) {
      console.error('Failed to load existing consultation:', err);
    }
  };

  const handleSaveConsultation = async () => {
    if (!selectedAppointment) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('token');

      if (activeConsultation) {
        // Update existing
        const response = await fetch(`/api/consultations/by-id/${activeConsultation.id}`, {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chief_complaint: consultationForm.chief_complaint,
            present_history: consultationForm.present_history,
            examination_findings: consultationForm.examination_findings,
            notes: consultationForm.notes,
            follow_up_date: consultationForm.follow_up_date || null
          })
        });
        if (response.ok) {
          const data = await response.json();
          setActiveConsultation(data);
          toast({ title: 'Success', description: 'Consultation updated successfully' });
        } else {
          toast({ variant: 'destructive', title: 'Error', description: 'Failed to update consultation' });
        }
      } else {
        // Create new
        const response = await fetch('/api/consultations/', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            patient_id: selectedAppointment.patient_id,
            appointment_id: selectedAppointment.id,
            consultation_type: selectedAppointment.appointment_type === 'followup' ? 'followup' : 'outpatient',
            chief_complaint: consultationForm.chief_complaint,
            present_history: consultationForm.present_history,
            examination_findings: consultationForm.examination_findings,
            consultation_fee: selectedAppointment.consultation_fee || 0,
            notes: consultationForm.notes
          })
        });
        if (response.ok) {
          const data = await response.json();
          setActiveConsultation(data);
          toast({ title: 'Success', description: 'Consultation record created successfully' });
        } else {
          const error = await response.json();
          toast({ variant: 'destructive', title: 'Error', description: error.detail || 'Failed to create consultation' });
        }
      }
    } catch (error) {
      console.error('Error saving consultation:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error saving consultation' });
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteConsultation = async () => {
    if (!activeConsultation) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/consultations/by-id/${activeConsultation.id}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: 'completed',
          follow_up_date: consultationForm.follow_up_date || null,
          chief_complaint: consultationForm.chief_complaint,
          present_history: consultationForm.present_history,
          examination_findings: consultationForm.examination_findings,
          notes: consultationForm.notes
        })
      });
      if (response.ok) {
        setShowConsultationDialog(false);
        toast({ title: 'Success', description: 'Consultation completed' });
      }
    } catch (error) {
      console.error('Error completing consultation:', error);
    } finally {
      setLoading(false);
    }
  };

  // --- Prescription ---
  const showPrintPreview = async (prescription) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/prescriptions-simple/${prescription.prescription_id}/download`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        setPreviewPrescription(prescription);
        setPreviewPdfUrl(url);
        setShowPrintPreviewDialog(true);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to load prescription preview' });
      }
    } catch (error) {
      console.error('Error loading prescription preview:', error);
    }
  };

  const refreshPreview = async () => {
    if (previewPrescription) {
      if (previewPdfUrl) {
        window.URL.revokeObjectURL(previewPdfUrl);
        setPreviewPdfUrl(null);
      }
      await showPrintPreview(previewPrescription);
    }
  };

  const printFromPreview = () => {
    if (previewPdfUrl) {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
      iframe.src = previewPdfUrl;
      iframe.onload = () => {
        iframe.contentWindow.print();
        setTimeout(() => document.body.removeChild(iframe), 1000);
      };
      closePrintPreview();
    }
  };

  const closePrintPreview = () => {
    if (previewPdfUrl) window.URL.revokeObjectURL(previewPdfUrl);
    setPreviewPdfUrl(null);
    setPreviewPrescription(null);
    setShowPrintPreviewDialog(false);
  };

  const submitPrescription = async () => {
    if (!selectedAppointment) return;

    try {
      setLoading(true);
      const token = localStorage.getItem('token');

      // Get patient UUID from appointment data directly
      const patient_uuid = selectedAppointment.patient_uuid;
      if (!patient_uuid) {
        toast({ variant: 'destructive', title: 'Error', description: 'Could not find patient information. Please try again.' });
        return;
      }

      const prescriptionData = {
        patient_id: patient_uuid,
        appointment_id: selectedAppointment.id,
        consultation_id: activeConsultation?.id || null,
        medicines: prescriptionForm.medications
          .filter(med => med.medicine_name && med.medicine_name.trim() !== '')
          .map(med => {
            const schedule = med.frequency_schedule || '1-0-0';
            const [morning, afternoon, night] = schedule.split('-');
            const timings = [];
            if (morning === '1') timings.push('morning');
            if (afternoon === '1') timings.push('afternoon');
            if (night === '1') timings.push('night');
            const frequencyText = timings.length > 0 ? timings.join(', ') : 'once daily';
            const foodTimingTexts = {
              'before_food': 'before food', 'after_food': 'after food',
              'with_food': 'with food', 'on_empty_stomach': 'on empty stomach', 'anytime': 'anytime'
            };
            const dosageInstruction = `${med.dosage || '1 dose'} - ${frequencyText} ${foodTimingTexts[med.food_timing] || 'after food'}`;
            return {
              medicine_id: med.medicine_id ? Number(med.medicine_id) : null,
              name: med.medicine_name,
              dosage: dosageInstruction,
              duration: med.duration || 'Complete course',
              instructions: med.instructions || 'Take as prescribed',
              quantity: med.quantity_prescribed ? `${med.quantity_prescribed} units` : '1 unit',
              frequency_schedule: med.frequency_schedule,
              food_timing: med.food_timing
            };
          }),
        diagnosis: prescriptionForm.diagnosis || '',
        notes: prescriptionForm.notes || ''
      };

      let response;
      if (createdPrescription?.prescription_id) {
        // Update existing prescription for this consultation
        response = await fetch(`/api/prescriptions-simple/${createdPrescription.prescription_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            medicines: prescriptionData.medicines,
            diagnosis: prescriptionData.diagnosis,
            notes: prescriptionData.notes
          })
        });
      } else {
        // Create new prescription
        response = await fetch('/api/prescriptions-simple/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify(prescriptionData)
        });
      }

      if (response.ok) {
        const result = await response.json();
        setCreatedPrescription(result);
        const action = createdPrescription?.prescription_id ? 'updated' : 'created';
        setSuccessMessage(`Prescription ${action} successfully! Prescription ID: ${result.prescription_id}`);
        setShowSuccessDialog(true);
        setShowPrescriptionDialog(false);

        // Also update follow-up on appointment if set
        if (prescriptionForm.follow_up_date) {
          try {
            await fetch(`/api/appointments/${selectedAppointment.id}/notes`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({
                notes: `${selectedAppointment.notes ? selectedAppointment.notes + '\n' : ''}Follow-up: ${prescriptionForm.follow_up_date}`
              })
            });
          } catch (e) { console.error('Error saving follow-up:', e); }
        }

        setPrescriptionForm({
          medications: [{
            medicine_id: '', medicine_name: '', quantity_prescribed: 1, dosage: '',
            frequency_schedule: '1-0-0', food_timing: 'after_food', duration: '', instructions: ''
          }],
          diagnosis: '', notes: '', follow_up_date: ''
        });
        fetchPrescriptions();
      } else {
        const error = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: `Error creating prescription: ${error.detail || 'Unknown error'}` });
      }
    } catch (error) {
      console.error('Error creating prescription:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateAppointmentStatus = async (appointmentId, status) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');

      // Use dedicated endpoints for status changes
      let url = `/api/appointments/${appointmentId}`;
      let method = 'PUT';
      let body = JSON.stringify({ status });

      if (status === 'in_progress') {
        url = `/api/appointments/${appointmentId}/start-consultation`;
        method = 'POST';
        body = undefined;
      } else if (status === 'no_show') {
        url = `/api/appointments/${appointmentId}/no-show`;
        method = 'POST';
        body = undefined;
      }

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        ...(body ? { body } : {})
      });

      if (response.ok) {
        fetchTodayAppointments(user?.id);
        fetchQueueData(user?.id);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Error updating appointment status' });
      }
    } catch (error) {
      console.error('Error:', error);
    }
    setLoading(false);
  };

  // --- Medication helpers ---
  const addMedication = () => {
    setPrescriptionForm(prev => ({
      ...prev,
      medications: [...prev.medications, {
        medicine_id: '', medicine_name: '', quantity_prescribed: 1, dosage: '',
        frequency_schedule: '1-0-0', food_timing: 'after_food', duration: '', instructions: ''
      }]
    }));
  };

  const updateMedication = (index, field, value) => {
    setPrescriptionForm(prev => ({
      ...prev,
      medications: prev.medications.map((med, i) => i === index ? { ...med, [field]: value } : med)
    }));
  };

  const removeMedication = (index) => {
    setPrescriptionForm(prev => ({
      ...prev,
      medications: prev.medications.filter((_, i) => i !== index)
    }));
  };

  // Lab helpers
  const fetchAvailableLabTests = async () => {
    try {
      const token = localStorage.getItem('token');
      const [testsRes, catsRes] = await Promise.all([
        fetch('/api/lab/tests', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/lab/categories', { headers: { Authorization: `Bearer ${token}` } })
      ]);
      if (testsRes.ok) setAvailableLabTests(await testsRes.json());
      if (catsRes.ok) setLabCategories(await catsRes.json());
    } catch (err) {
      console.error('Failed to fetch lab tests:', err);
    }
  };

  const fetchLabOrders = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/lab/orders', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setLabOrders(await res.json());
    } catch (err) {
      console.error('Failed to fetch lab orders:', err);
    }
  };

  const handleSubmitLabOrder = async (force = false) => {
    if (!selectedAppointment || (selectedLabTests.length === 0 && customLabTests.length === 0)) return;
    setLabOrderSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      // Build notes: combine doctor notes + custom test names
      let combinedNotes = labOrderNotes || '';
      if (customLabTests.length > 0) {
        const customNote = `Other tests requested: ${customLabTests.join(', ')}`;
        combinedNotes = combinedNotes ? `${combinedNotes}\n${customNote}` : customNote;
      }

      // Submit catalog tests via API
      if (selectedLabTests.length > 0) {
        const res = await fetch('/api/lab/orders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            patient_id: selectedAppointment.patient_id,
            appointment_id: selectedAppointment.id,
            test_ids: selectedLabTests,
            priority: labOrderPriority,
            force: force,
            notes: combinedNotes || null
          })
        });
        if (res.status === 409) {
          const err = await res.json();
          setLabDuplicateWarning(err.detail?.duplicates || []);
          setLabOrderSubmitting(false);
          return;
        }
        if (!res.ok) {
          const err = await res.json();
          toast({ variant: 'destructive', title: 'Error', description: typeof err.detail === 'string' ? err.detail : 'Failed to create lab orders' });
          setLabOrderSubmitting(false);
          return;
        }
      }

      setShowLabOrderDialog(false);
      setSelectedLabTests([]);
      setCustomLabTests([]);
      setCustomLabTestInput('');
      setLabOrderPriority('normal');
      setLabOrderNotes('');
      fetchLabOrders();
      const count = selectedLabTests.length + customLabTests.length;
      toast({ title: 'Success', description: `${count} lab order(s) created successfully${customLabTests.length > 0 ? '. Custom tests have been noted for the lab team.' : ''}` });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to create lab orders' });
    } finally {
      setLabOrderSubmitting(false);
    }
  };

  const addCustomLabTest = () => {
    const name = customLabTestInput.trim();
    if (name && !customLabTests.includes(name)) {
      setCustomLabTests(prev => [...prev, name]);
      setCustomLabTestInput('');
    }
  };

  const removeCustomLabTest = (name) => {
    setCustomLabTests(prev => prev.filter(t => t !== name));
  };

  const openLabReport = async (reportId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/reports/${reportId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setViewingLabReport(await res.json());
        setShowLabReportDialog(true);
      }
    } catch (err) {
      console.error('Failed to fetch report:', err);
    }
  };

  const toggleLabTestSelection = (testId) => {
    setSelectedLabTests(prev =>
      prev.includes(testId) ? prev.filter(id => id !== testId) : [...prev, testId]
    );
  };

  const filteredLabTests = availableLabTests.filter(t => {
    if (!t.is_active) return false;
    if (labCategoryFilter !== 'all' && String(t.category_id) !== labCategoryFilter) return false;
    if (labSearchQuery) {
      const q = labSearchQuery.toLowerCase();
      return t.name.toLowerCase().includes(q) || t.test_code.toLowerCase().includes(q);
    }
    return true;
  });

  // --- Status helpers ---
  const getStatusColor = (status) => {
    const colors = {
      scheduled: 'bg-blue-100 text-blue-800',
      confirmed: 'bg-green-100 text-green-800',
      in_progress: 'bg-yellow-100 text-yellow-800',
      completed: 'bg-gray-100 text-gray-800',
      cancelled: 'bg-red-100 text-red-800',
      no_show: 'bg-orange-100 text-orange-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getStatusLabel = (status) => {
    const labels = {
      scheduled: 'Scheduled', confirmed: 'Checked In', in_progress: 'In Progress',
      completed: 'Completed', cancelled: 'Cancelled', no_show: 'No Show'
    };
    return labels[status] || status;
  };

  const getPriorityColor = (priority) => {
    const colors = { normal: 'bg-blue-100 text-blue-800', urgent: 'bg-orange-100 text-orange-800', emergency: 'bg-red-100 text-red-800' };
    return colors[priority] || 'bg-gray-100 text-gray-800';
  };

  const getTimeSlotStatus = (appointmentTime, status) => {
    if (status === 'completed') return 'completed';
    if (status === 'cancelled' || status === 'no_show') return 'cancelled';
    if (!appointmentTime) return 'scheduled';
    const currentTime = new Date();
    const [hours, minutes] = appointmentTime.split(':');
    const appointmentDate = new Date();
    appointmentDate.setHours(parseInt(hours, 10), parseInt(minutes, 10));
    if (appointmentDate < currentTime) return 'overdue';
    if (appointmentDate.getTime() - currentTime.getTime() <= 30 * 60 * 1000) return 'upcoming';
    return 'scheduled';
  };

  // --- Summary stats ---
  const stats = {
    total: appointments.length,
    scheduled: appointments.filter(a => a.status === 'scheduled').length,
    checked_in: appointments.filter(a => a.status === 'confirmed').length,
    in_progress: appointments.filter(a => a.status === 'in_progress').length,
    completed: appointments.filter(a => a.status === 'completed').length,
    no_show: appointments.filter(a => a.status === 'no_show').length,
  };

  // Lab order stats
  const labStats = {
    total: labOrders.length,
    ordered: labOrders.filter(o => o.status === 'ordered').length,
    processing: labOrders.filter(o => o.status === 'processing' || o.status === 'collected').length,
    completed: labOrders.filter(o => o.status === 'completed').length,
    withReport: labOrders.filter(o => o.status === 'completed' && o.has_report).length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Doctor Dashboard</h1>
          {user && (
            <p className="text-gray-600">
              Welcome, Dr. {user.full_name} - {user.specialization || 'General Medicine'}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">
            Last refreshed: {lastRefreshed.toLocaleTimeString()}
          </span>
          <Button variant="outline" size="sm" onClick={() => {
            fetchTodayAppointments(user?.id);
            fetchQueueData(user?.id);
            setLastRefreshed(new Date());
          }}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Summary Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.total}</div>
            <div className="text-xs text-gray-500">Total</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-500">{stats.scheduled}</div>
            <div className="text-xs text-gray-500">Scheduled</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.checked_in}</div>
            <div className="text-xs text-gray-500">Checked In</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">{stats.in_progress}</div>
            <div className="text-xs text-gray-500">In Progress</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-gray-600">{stats.completed}</div>
            <div className="text-xs text-gray-500">Completed</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-orange-600">{stats.no_show}</div>
            <div className="text-xs text-gray-500">No Show</div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions + Reports Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Queue Info */}
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="p-4">
            <h3 className="text-sm font-semibold text-gray-500 mb-2">CURRENT QUEUE</h3>
            {queueData && queueData.queue && queueData.queue.length > 0 ? (
              <>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <Hash className="h-5 w-5 text-blue-600" />
                    <div>
                      {queueData.current_patient ? (
                        <span className="font-medium text-blue-700">
                          Token #{queueData.current_patient.token_number} - {queueData.current_patient.patient_name}
                        </span>
                      ) : (
                        <span className="text-gray-500">No patient in consultation</span>
                      )}
                    </div>
                  </div>
                  <Badge variant="outline">{queueData.queue.filter(q => q.status === 'confirmed' && q.token_status !== 'skipped').length} waiting</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => queueAction('call-next')}>
                    Call Next
                  </Button>
                  {queueData.current_patient && (
                    <Button size="sm" variant="outline" onClick={() => queueAction('skip', queueData.current_patient.appointment_id)}>
                      Skip Current
                    </Button>
                  )}
                  {queueData.queue.filter(q => q.token_status === 'skipped').map(s => (
                    <Button key={s.appointment_id} size="sm" variant="secondary" onClick={() => queueAction('recall', s.appointment_id)}>
                      Recall #{s.token_number}
                    </Button>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-400">No patients in queue</p>
            )}
          </CardContent>
        </Card>

        {/* Lab Reports Quick View */}
        <Card className="border-l-4 border-l-purple-500">
          <CardContent className="p-4">
            <h3 className="text-sm font-semibold text-gray-500 mb-2">LAB ORDERS STATUS</h3>
            <div className="flex items-center justify-between">
              <div className="flex gap-4 text-sm">
                <span><span className="font-bold text-blue-600">{labStats.ordered}</span> <span className="text-gray-500">Pending</span></span>
                <span><span className="font-bold text-yellow-600">{labStats.processing}</span> <span className="text-gray-500">Processing</span></span>
                <span><span className="font-bold text-green-600">{labStats.withReport}</span> <span className="text-gray-500">Reports Ready</span></span>
              </div>
              {labStats.withReport > 0 && (
                <Button size="sm" variant="outline" onClick={() => setActiveTab('lab-orders')}>
                  <Eye className="h-3.5 w-3.5 mr-1" /> View Reports
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardContent className="p-4">
          <h3 className="text-sm font-semibold text-gray-500 mb-3">QUICK ACTIONS</h3>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/ehr')}>
              <FileText className="h-4 w-4 mr-1" /> Patient Records (EHR)
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/availability')}>
              <Calendar className="h-4 w-4 mr-1" /> Manage Availability
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setActiveTab('lab-orders'); }}>
              <TestTube className="h-4 w-4 mr-1" /> Lab Orders ({labStats.total})
            </Button>
            {labStats.withReport > 0 && (
              <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => setActiveTab('lab-orders')}>
                <CheckCircle className="h-4 w-4 mr-1" /> {labStats.withReport} Lab Report(s) Ready
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className={`grid w-full ${inpatientEnabled ? 'grid-cols-4' : 'grid-cols-3'}`}>
          <TabsTrigger value="appointments">Today's Schedule</TabsTrigger>
          <TabsTrigger value="prescriptions">Prescriptions</TabsTrigger>
          <TabsTrigger value="lab-orders">
            Lab Orders
            {labStats.withReport > 0 && (
              <Badge className="ml-1.5 bg-green-500 text-white text-xs px-1.5">{labStats.withReport}</Badge>
            )}
          </TabsTrigger>
          {inpatientEnabled && (
            <TabsTrigger value="inpatients">
              Inpatient
              {doctorAdmissions.length > 0 && (
                <Badge className="ml-1.5 bg-blue-500 text-white text-xs px-1.5">{doctorAdmissions.length}</Badge>
              )}
            </TabsTrigger>
          )}
        </TabsList>

        {/* Appointments Tab */}
        <TabsContent value="appointments" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  Appointment Schedule - {format(new Date(), 'EEEE, MMMM do, yyyy')}
                </CardTitle>
                <Button
                  variant="outline" size="sm"
                  onClick={() => {
                    setShowCompletedAppointments(true);
                    fetchCompletedAppointments(user?.id);
                  }}
                >
                  <Info className="h-4 w-4 mr-2" /> View Completed
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {appointments.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">No appointments scheduled for today</p>
                ) : (
                  appointments.map((appointment) => {
                    const timeStatus = getTimeSlotStatus(appointment.appointment_time, appointment.status);
                    return (
                      <Card
                        key={appointment.id}
                        className={`border-l-4 ${
                          timeStatus === 'overdue' ? 'border-l-red-500' :
                          timeStatus === 'upcoming' ? 'border-l-yellow-500' :
                          timeStatus === 'completed' ? 'border-l-green-500' :
                          timeStatus === 'cancelled' ? 'border-l-gray-300' :
                          'border-l-blue-500'
                        }`}
                      >
                        <CardContent className="pt-4">
                          <div className="flex justify-between items-start">
                            <div className="space-y-2 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                {appointment.token_number && (
                                  <Badge variant="outline" className="bg-blue-50 text-blue-700 font-mono">
                                    <Hash className="h-3 w-3 mr-1" />#{appointment.token_number}
                                  </Badge>
                                )}
                                <h3 className="font-semibold text-lg">{appointment.patient_name}</h3>
                                <Badge className={getPriorityColor(appointment.priority)}>
                                  {appointment.priority}
                                </Badge>
                                <Badge className={getStatusColor(appointment.status)}>
                                  {getStatusLabel(appointment.status)}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-4 text-sm text-gray-600">
                                <span className="flex items-center gap-1">
                                  <Clock className="h-4 w-4" />
                                  {formatTime(appointment.appointment_time)} ({appointment.duration_minutes} min)
                                </span>
                                <span>#{appointment.appointment_number}</span>
                              </div>
                              <div className="text-sm text-gray-600">
                                <strong>Type:</strong> {appointment.appointment_type}
                                {appointment.reason && (
                                  <> &middot; <strong>Reason:</strong> {appointment.reason}</>
                                )}
                              </div>
                              {appointment.notes && (
                                <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded">
                                  <strong>Notes:</strong> {appointment.notes}
                                </div>
                              )}
                            </div>
                            <div className="flex flex-wrap gap-2 ml-4 justify-end max-w-[320px]">
                              <Button size="sm" variant="outline" onClick={() => fetchPatientHistory(appointment)}>
                                <History className="h-4 w-4 mr-1" /> History
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => openNotesDialog(appointment)}>
                                <FileText className="h-4 w-4 mr-1" /> Notes
                              </Button>

                              {appointment.status === 'scheduled' && (
                                <>
                                  <Button size="sm" variant="outline"
                                    onClick={() => updateAppointmentStatus(appointment.id, 'confirmed')}
                                    disabled={loading}>
                                    <CheckCircle className="h-4 w-4 mr-1" /> Confirm
                                  </Button>
                                  <Button size="sm"
                                    onClick={() => updateAppointmentStatus(appointment.id, 'in_progress')}
                                    disabled={loading}>
                                    Start Consultation
                                  </Button>
                                </>
                              )}
                              {appointment.status === 'confirmed' && (
                                <Button size="sm"
                                  onClick={() => updateAppointmentStatus(appointment.id, 'in_progress')}
                                  disabled={loading}>
                                  Start Consultation
                                </Button>
                              )}
                              {appointment.status === 'in_progress' && (
                                <>
                                  <Button size="sm" variant="outline"
                                    onClick={() => navigate(`/dashboard/consultation?appointmentId=${appointment.id}&patientId=${appointment.patient_id}&patientUuid=${appointment.patient_uuid || ''}&patientName=${encodeURIComponent(appointment.patient_name)}`)}>
                                    <Stethoscope className="h-4 w-4 mr-1" /> Consult
                                  </Button>
                                  <Button size="sm" className="bg-green-600 hover:bg-green-700"
                                    onClick={() => updateAppointmentStatus(appointment.id, 'completed')}
                                    disabled={loading}>
                                    <CheckCircle className="h-4 w-4 mr-1" /> Complete
                                  </Button>
                                </>
                              )}
                              {(appointment.status === 'scheduled' || appointment.status === 'confirmed') && (
                                <Button size="sm" variant="destructive"
                                  onClick={() => updateAppointmentStatus(appointment.id, 'cancelled')}
                                  disabled={loading}>
                                  <XCircle className="h-4 w-4 mr-1" /> Cancel
                                </Button>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Prescriptions Tab */}
        <TabsContent value="prescriptions" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Pill className="h-5 w-5" />
                  My Prescriptions ({prescriptions.length})
                </span>
                <Button onClick={fetchPrescriptions} variant="outline" size="sm">
                  <RefreshCw className="h-4 w-4 mr-2" /> Refresh
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {prescriptions.length === 0 ? (
                <div className="text-center py-8">
                  <Pill className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-500">No prescriptions created yet</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {prescriptions.map((rx) => {
                    const rxKey = rx.id;
                    const isExpanded = expandedRxGroups[rxKey];
                    const rxDate = rx.prescription_date
                      ? format(new Date(rx.prescription_date), 'dd MMM yyyy')
                      : 'Unknown date';
                    const medCount = rx.medicines?.length || 0;
                    return (
                      <div key={rxKey} className="border rounded-lg overflow-hidden">
                        <div
                          className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors"
                          onClick={() => setExpandedRxGroups(prev => ({ ...prev, [rxKey]: !prev[rxKey] }))}
                        >
                          {isExpanded
                            ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                            : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                          }
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-medium text-gray-800">Prescription on {rxDate}</span>
                              <span className="text-xs text-gray-500">— {rx.patient_name}</span>
                              <Badge variant="outline" className="text-xs">{medCount} medicine{medCount !== 1 ? 's' : ''}</Badge>
                              <Badge className={
                                rx.status === 'active' ? 'bg-green-100 text-green-700 text-xs' :
                                rx.status === 'cancelled' ? 'bg-red-100 text-red-700 text-xs' :
                                'bg-gray-100 text-gray-600 text-xs'
                              }>{rx.status}</Badge>
                            </div>
                            {rx.diagnosis && !isExpanded && (
                              <p className="text-xs text-gray-500 mt-0.5 truncate">Dx: {rx.diagnosis}</p>
                            )}
                          </div>
                          <Button size="sm" variant="ghost" className="h-7 px-2 flex-shrink-0"
                            onClick={(e) => { e.stopPropagation(); showPrintPreview(rx); }}>
                            <Printer className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        {isExpanded && (
                          <div className="border-t bg-gray-50 px-4 py-3">
                            <div className="space-y-2">
                              {rx.medicines?.map((medicine, idx) => (
                                <div key={idx} className="flex items-start gap-2 text-sm">
                                  <span className="text-gray-400 mt-0.5 flex-shrink-0">{idx + 1}.</span>
                                  <div className="flex-1">
                                    <span className="font-medium text-gray-800">{medicine.name}</span>
                                    <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap gap-x-3">
                                      {medicine.dosage && <span>Dosage: {medicine.dosage}</span>}
                                      {medicine.frequency_schedule && <span>Schedule: {medicine.frequency_schedule}</span>}
                                      {medicine.duration && <span>Duration: {medicine.duration}</span>}
                                      {medicine.food_timing && <span>{medicine.food_timing.replace(/_/g, ' ')}</span>}
                                      {medicine.quantity && <span>Qty: {medicine.quantity}</span>}
                                    </div>
                                    {medicine.instructions && <p className="text-xs text-gray-400 mt-0.5">{medicine.instructions}</p>}
                                  </div>
                                </div>
                              ))}
                            </div>
                            {(rx.diagnosis || rx.notes) && (
                              <div className="mt-3 pt-2 border-t border-gray-200 text-sm">
                                {rx.diagnosis && <p><strong className="text-gray-700">Diagnosis:</strong> <span className="text-gray-600">{rx.diagnosis}</span></p>}
                                {rx.notes && <p className="mt-1"><strong className="text-gray-700">Notes:</strong> <span className="text-gray-600">{rx.notes}</span></p>}
                              </div>
                            )}
                            <div className="mt-3 flex justify-end">
                              <Button size="sm" variant="outline" onClick={() => showPrintPreview(rx)}>
                                <Eye className="h-3.5 w-3.5 mr-1" /> Preview & Print
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Lab Orders Tab */}
        <TabsContent value="lab-orders" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <TestTube className="h-5 w-5" />
                  Lab Orders
                </span>
                <Button variant="outline" size="sm" onClick={fetchLabOrders}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {labOrders.length === 0 ? (
                <div className="text-center py-8">
                  <TestTube className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">No lab orders yet.</p>
                  <p className="text-sm text-gray-400 mt-1">Order lab tests from the appointment card during consultation.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Pending orders — flat list */}
                  {labOrders.filter(o => !['completed', 'cancelled'].includes(o.status)).length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-2">
                        <Clock className="h-4 w-4" /> Pending Orders
                      </h3>
                      <div className="space-y-1">
                        {labOrders.filter(o => !['completed', 'cancelled'].includes(o.status)).map(order => (
                          <div key={order.id} className="flex items-center justify-between p-2.5 border rounded-lg text-sm bg-amber-50/50">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{order.patient_name}</span>
                                <span className="text-gray-500">—</span>
                                <span>{order.test_name}</span>
                                <Badge variant="outline" className="text-xs">{order.test_code}</Badge>
                                {order.priority !== 'normal' && (
                                  <Badge variant="destructive" className="text-xs">{order.priority.toUpperCase()}</Badge>
                                )}
                              </div>
                              <p className="text-xs text-gray-500 mt-0.5">
                                #{order.order_number}
                                {order.order_date && ` | ${format(new Date(order.order_date), 'dd MMM yyyy, hh:mm a')}`}
                              </p>
                            </div>
                            <Badge className={
                              order.status === 'processing' ? 'bg-purple-100 text-purple-700' :
                              order.status === 'collected' ? 'bg-yellow-100 text-yellow-700' :
                              'bg-blue-100 text-blue-700'
                            }>{order.status}</Badge>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Completed results — grouped by date, collapsible */}
                  {labOrders.filter(o => o.status === 'completed' && o.has_report).length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-2">
                        <History className="h-4 w-4" /> Completed Results
                      </h3>
                      <div className="space-y-1.5">
                        {(() => {
                          const completedOrders = labOrders.filter(o => o.status === 'completed' && o.has_report);
                          // Group by date + patient
                          const grouped = {};
                          completedOrders.forEach(order => {
                            const dateKey = order.order_date
                              ? format(new Date(order.order_date), 'yyyy-MM-dd')
                              : 'unknown';
                            const groupKey = `${dateKey}_${order.patient_name}`;
                            if (!grouped[groupKey]) grouped[groupKey] = { date: dateKey, patientName: order.patient_name, orders: [] };
                            grouped[groupKey].orders.push(order);
                          });
                          const sortedKeys = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

                          return sortedKeys.map(groupKey => {
                            const group = grouped[groupKey];
                            const isExpanded = expandedLabGroups[groupKey];
                            const displayDate = group.date !== 'unknown'
                              ? format(new Date(group.date), 'dd MMM yyyy')
                              : 'Unknown date';

                            return (
                              <div key={groupKey} className="border rounded-lg overflow-hidden">
                                <div
                                  className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors"
                                  onClick={() => setExpandedLabGroups(prev => ({ ...prev, [groupKey]: !prev[groupKey] }))}
                                >
                                  {isExpanded
                                    ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                                    : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                                  }
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="text-sm font-medium text-gray-800">Consultation on {displayDate}</span>
                                      <span className="text-xs text-gray-500">— {group.patientName}</span>
                                      <Badge variant="outline" className="text-xs">{group.orders.length} test{group.orders.length !== 1 ? 's' : ''}</Badge>
                                      <Badge className="bg-green-100 text-green-700 text-xs">Completed</Badge>
                                    </div>
                                    {!isExpanded && (
                                      <p className="text-xs text-gray-500 mt-0.5 truncate">
                                        {group.orders.map(o => o.test_name).join(', ')}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                {isExpanded && (
                                  <div className="border-t bg-gray-50">
                                    {group.orders.map((order, oIdx) => (
                                      <div key={order.id} className={`flex items-center justify-between px-4 py-2.5 ${oIdx > 0 ? 'border-t border-gray-200' : ''} hover:bg-gray-100 transition-colors`}>
                                        <div className="flex items-center gap-2">
                                          <TestTube className="h-3.5 w-3.5 text-gray-400" />
                                          <span className="text-sm font-medium">{order.test_name}</span>
                                          <Badge variant="outline" className="text-[10px]">{order.test_code}</Badge>
                                        </div>
                                        <Button size="sm" variant="outline" className="h-7" onClick={() => openLabReport(order.report_id)}>
                                          <Eye className="h-3.5 w-3.5 mr-1" /> View Report
                                        </Button>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          });
                        })()}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Inpatient Patients Tab */}
        {inpatientEnabled && (
          <TabsContent value="inpatients" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="flex items-center gap-2">
                    <Bed className="h-5 w-5" /> My Inpatient Patients
                  </CardTitle>
                  <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/inpatient/discharge-history')}>
                    <History className="h-3.5 w-3.5 mr-1" /> Full discharge history
                  </Button>
                </div>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    variant={inpatientListTab === 'active' ? 'default' : 'outline'}
                    onClick={() => setInpatientListTab('active')}
                  >
                    Currently admitted ({doctorAdmissions.length})
                  </Button>
                  <Button
                    size="sm"
                    variant={inpatientListTab === 'discharged' ? 'default' : 'outline'}
                    onClick={() => setInpatientListTab('discharged')}
                  >
                    Discharged ({doctorDischargedAdmissions.length})
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {inpatientListTab === 'active' ? (
                  doctorAdmissions.length === 0 ? (
                    <p className="text-gray-500 text-center py-4">No inpatient patients assigned to you.</p>
                  ) : (
                    <div className="space-y-3">
                      {doctorAdmissions.map(adm => {
                        const stayDays = adm.admission_date ? Math.max(1, Math.floor((Date.now() - new Date(adm.admission_date).getTime()) / 86400000)) : 0;
                        return (
                          <div key={adm.id} className="border rounded-lg p-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer" onClick={() => openManageAdmission(adm)}>
                            <div className="flex items-center gap-4 flex-wrap">
                              <div>
                                <div className="font-medium text-sm">{adm.patient_name || 'N/A'}</div>
                                <div className="text-xs text-gray-500">{adm.admission_number}</div>
                              </div>
                              <Badge variant="outline" className="text-xs">{adm.room_number}{adm.bed_label ? ` / ${adm.bed_label}` : adm.bed_number ? ` / ${adm.bed_number}` : ''}</Badge>
                              <Badge variant="outline" className="text-xs">{adm.admission_type}</Badge>
                              <span className="text-xs text-gray-500">Day {stayDays}</span>
                              <span className="text-xs text-gray-500">{adm.condition_on_admission || ''}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button size="sm" variant="outline" onClick={(e) => openDischargeSummary(adm, e)} title="Write discharge summary for reception">
                                <FileText className="h-3.5 w-3.5 mr-1" /> Discharge
                              </Button>
                              <Button size="sm" onClick={(e) => { e.stopPropagation(); openManageAdmission(adm); }}>
                                <Stethoscope className="h-3.5 w-3.5 mr-1" /> Manage
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )
                ) : (
                  doctorDischargedAdmissions.length === 0 ? (
                    <p className="text-gray-500 text-center py-4">No discharged inpatients on your record yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {doctorDischargedAdmissions.map(adm => (
                        <div key={adm.id} className="border rounded-lg p-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer" onClick={() => openManageAdmission(adm)}>
                          <div className="flex items-center gap-4 flex-wrap">
                            <div>
                              <div className="font-medium text-sm">{adm.patient_name || 'N/A'}</div>
                              <div className="text-xs text-gray-500">{adm.admission_number}</div>
                            </div>
                            <Badge className="bg-green-100 text-green-800 text-xs">Discharged</Badge>
                            <span className="text-xs text-gray-500">
                              {adm.discharge_date ? new Date(adm.discharge_date).toLocaleDateString() : '—'}
                            </span>
                            <Badge variant="outline" className="text-xs capitalize">
                              {(adm.discharge_type || 'normal').replace(/_/g, ' ')}
                            </Badge>
                            {adm.summaryStatus && DISCHARGE_SUMMARY_STATUS[adm.summaryStatus] && (
                              <Badge className={`text-xs ${DISCHARGE_SUMMARY_STATUS[adm.summaryStatus].className}`}>
                                {DISCHARGE_SUMMARY_STATUS[adm.summaryStatus].listLabel
                                  || DISCHARGE_SUMMARY_STATUS[adm.summaryStatus].label}
                              </Badge>
                            )}
                          </div>
                          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); openManageAdmission(adm); }}>
                            View details
                          </Button>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {/* ============================================================ */}
      {/* MANAGE ADMISSION POPUP — comprehensive inpatient view for doctor */}
      {/* ============================================================ */}
      <Dialog open={showManageAdmissionDialog} onOpenChange={(o) => { setShowManageAdmissionDialog(o); if (!o) setWardRoundAdmission(null); }}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bed className="h-5 w-5" /> {wardRoundAdmission?.patient_name || 'Admission'}
              {wardRoundAdmission && (
                <span className="text-sm font-normal text-gray-500 ml-1">
                  · {wardRoundAdmission.admission_number}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>

          {wardRoundAdmission && (
            <div className="space-y-4">
              {/* Summary strip */}
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant="outline">Room {wardRoundAdmission.room_number}{wardRoundAdmission.bed_label ? ` / ${wardRoundAdmission.bed_label}` : wardRoundAdmission.bed_number ? ` / ${wardRoundAdmission.bed_number}` : ''}</Badge>
                <Badge variant="outline">{wardRoundAdmission.admission_type}</Badge>
                {wardRoundIsDischarged ? (
                  <Badge className="bg-green-100 text-green-800">Discharged</Badge>
                ) : (
                  <Badge variant="outline">Day {wardRoundAdmission.admission_date ? Math.max(1, Math.floor((Date.now() - new Date(wardRoundAdmission.admission_date).getTime()) / 86400000)) : 0}</Badge>
                )}
                {wardRoundAdmission.condition_on_admission && <Badge variant="outline">{wardRoundAdmission.condition_on_admission}</Badge>}
                {wardRoundAdmission.is_mlc && <Badge className="bg-red-100 text-red-800">MLC</Badge>}
                {wardRoundAdmission.is_readmission && <Badge className="bg-orange-100 text-orange-800">Readmission</Badge>}
                {wardRoundIsDischarged && wardRoundAdmission.discharge_date && (
                  <Badge variant="outline">
                    Out {new Date(wardRoundAdmission.discharge_date).toLocaleDateString()}
                  </Badge>
                )}
              </div>

              {/* Allergies banner */}
              {wardRoundAllergies.length > 0 && (
                <div className="border-l-4 border-red-500 bg-red-50 p-2 rounded text-xs">
                  <div className="font-semibold text-red-800 flex items-center gap-1 mb-1"><AlertCircle className="h-3.5 w-3.5" /> Allergies</div>
                  <div className="flex flex-wrap gap-1">
                    {wardRoundAllergies.map(a => (
                      <span key={a.id} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium ${
                        a.severity === 'anaphylaxis' ? 'bg-red-200 text-red-900' :
                        a.severity === 'severe' ? 'bg-red-100 text-red-800' :
                        a.severity === 'moderate' ? 'bg-orange-100 text-orange-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`} title={a.reaction || ''}>
                        {a.allergen} ({a.severity})
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Quick actions */}
              <div className="flex flex-wrap gap-2 border-y py-2">
                {!wardRoundIsDischarged && (
                  <>
                    <Button size="sm" onClick={() => { setDoctorVisitAdmission(wardRoundAdmission); setDoctorVisitNotes(''); setShowDoctorVisitDialog(true); }}>
                      <Plus className="h-3.5 w-3.5 mr-1" /> Record Visit
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => {
                      setInpatientRxForm({ notes: '', items: [{ ...RX_BLANK_ITEM }] });
                      setShowInpatientRxDialog(true);
                    }}>
                      <Pill className="h-3.5 w-3.5 mr-1" /> Add Prescription
                    </Button>
                    <Button size="sm" variant="outline" onClick={openInpatientLabDialog}>
                      <TestTube className="h-3.5 w-3.5 mr-1" /> Order Lab Test
                    </Button>
                  </>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={openDischargeSummaryEditor}
                  title={wardRoundIsDischarged ? 'View discharge summary' : 'Write discharge summary for reception'}
                >
                  <FileText className="h-3.5 w-3.5 mr-1" />
                  {wardRoundIsDischarged ? 'View discharge summary'
                    : wardRoundSummaryStatus === 'ready' ? 'Edit submitted summary'
                      : 'Discharge'}
                </Button>
                {summaryReadyForPrint && (
                  <Button size="sm" variant="outline" onClick={printWardRoundDischargeSummary}>
                    <Printer className="h-3.5 w-3.5 mr-1" /> Print discharge summary
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={printWardRoundAdmissionDetail}>
                  <Printer className="h-3.5 w-3.5 mr-1" /> Detailed summary
                </Button>
                <Button size="sm" variant="ghost" onClick={refreshManageAdmission} className="ml-auto">
                  <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
                </Button>
              </div>

              <DischargeSummaryPreviewCard
                summary={wardRoundSummary}
                canWrite={!wardRoundIsDischarged}
                readOnly={wardRoundIsDischarged || wardRoundSummaryStatus === 'locked'}
                onEdit={openDischargeSummaryEditor}
                onPrint={summaryReadyForPrint ? printWardRoundDischargeSummary : undefined}
              />

              {/* Tabs */}
              <Tabs value={wardRoundTab} onValueChange={setWardRoundTab}>
                <TabsList className="grid w-full grid-cols-6 text-xs">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="visits">Visits ({wardRoundVisits.length})</TabsTrigger>
                  <TabsTrigger value="vitals">Vitals ({wardRoundVitals.length})</TabsTrigger>
                  <TabsTrigger value="rx">Rx ({wardRoundPrescriptions.length})</TabsTrigger>
                  <TabsTrigger value="labs">Labs ({wardRoundLabOrders.length})</TabsTrigger>
                  <TabsTrigger value="nursing">Nursing ({wardRoundNursingNotes.length})</TabsTrigger>
                </TabsList>

                {/* Overview */}
                <TabsContent value="overview" className="mt-3 space-y-2 text-sm">
                  <div className="grid grid-cols-2 gap-3">
                    <div><span className="text-gray-500 text-xs">Admitted on</span><div>{wardRoundAdmission.admission_date ? new Date(wardRoundAdmission.admission_date).toLocaleString() : '—'}</div></div>
                    <div><span className="text-gray-500 text-xs">Estimated stay</span><div>{wardRoundAdmission.estimated_stay_days ? `${wardRoundAdmission.estimated_stay_days} days` : '—'}</div></div>
                    <div className="col-span-2"><span className="text-gray-500 text-xs">Admission reason</span><div>{wardRoundAdmission.admission_reason || '—'}</div></div>
                    <div className="col-span-2"><span className="text-gray-500 text-xs">Notes</span><div className="whitespace-pre-wrap">{wardRoundAdmission.admission_notes || '—'}</div></div>
                    {wardRoundAdmission.admission_type === 'emergency' && (
                      <>
                        <div><span className="text-gray-500 text-xs">Triage</span><div>Level {wardRoundAdmission.triage_level || '—'}</div></div>
                        <div><span className="text-gray-500 text-xs">Arrival</span><div>{wardRoundAdmission.arrival_mode || '—'}</div></div>
                        <div className="col-span-2"><span className="text-gray-500 text-xs">Chief complaint</span><div>{wardRoundAdmission.chief_complaint || '—'}</div></div>
                      </>
                    )}
                  </div>
                </TabsContent>

                {/* Visits */}
                <TabsContent value="visits" className="mt-3">
                  {wardRoundVisits.length === 0 ? (
                    <p className="text-xs text-gray-500 text-center py-4">No visits recorded.</p>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {wardRoundVisits.map(v => (
                        <div key={v.id} className="border rounded p-2 text-xs bg-white">
                          <div className="flex justify-between">
                            <span className="font-medium">{v.visit_type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                            <span className="text-gray-400">{v.visit_datetime ? new Date(v.visit_datetime).toLocaleString() : ''}</span>
                          </div>
                          <div className="text-gray-500">by {v.visitor_name || 'N/A'}</div>
                          {v.notes && <p className="mt-1 text-gray-700 whitespace-pre-wrap">{v.notes}</p>}
                          {v.plan_for_today && (
                            <p className="mt-1 text-gray-700 italic"><b>Plan:</b> {v.plan_for_today}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Vitals */}
                <TabsContent value="vitals" className="mt-3">
                  {wardRoundVitals.length === 0 ? (
                    <p className="text-xs text-gray-500 text-center py-4">No vitals recorded.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs border-collapse">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="text-left p-1.5 border-b">When</th>
                            <th className="p-1.5 border-b">Shift</th>
                            <th className="p-1.5 border-b">BP</th>
                            <th className="p-1.5 border-b">HR</th>
                            <th className="p-1.5 border-b">RR</th>
                            <th className="p-1.5 border-b">SpO2</th>
                            <th className="p-1.5 border-b">Temp</th>
                            <th className="p-1.5 border-b">Pain</th>
                            <th className="p-1.5 border-b">By</th>
                          </tr>
                        </thead>
                        <tbody>
                          {wardRoundVitals.map(v => (
                            <tr key={v.id} className={v.is_abnormal ? 'bg-red-50' : ''}>
                              <td className="p-1.5 border-b">{v.recorded_at ? new Date(v.recorded_at).toLocaleString() : ''}</td>
                              <td className="p-1.5 border-b text-center">{v.shift || '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.bp_systolic && v.bp_diastolic ? `${v.bp_systolic}/${v.bp_diastolic}` : '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.heart_rate || '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.respiratory_rate || '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.spo2 || '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.temperature_c ? `${v.temperature_c}°C` : '—'}</td>
                              <td className="p-1.5 border-b text-center">{v.pain_score != null ? v.pain_score : '—'}</td>
                              <td className="p-1.5 border-b">{v.recorded_by_name || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </TabsContent>

                {/* Prescriptions */}
                <TabsContent value="rx" className="mt-3">
                  {wardRoundPrescriptions.length === 0 ? (
                    <p className="text-xs text-gray-500 text-center py-4">No prescriptions linked to this admission.</p>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {wardRoundPrescriptions.map(rx => (
                        <div key={`${rx.type}-${rx.id}`} className="border rounded p-2 text-xs bg-white">
                          <div className="flex justify-between mb-1">
                            <span className="font-medium">{rx.prescription_number}</span>
                            <Badge className={rx.status === 'dispensed' ? 'bg-green-100 text-green-800' : rx.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'}>{rx.status}</Badge>
                          </div>
                          <div className="text-gray-500">by {rx.doctor_name} · {rx.date ? new Date(rx.date).toLocaleString() : ''}</div>
                          {rx.medicines?.length > 0 && (
                            <div className="bg-gray-50 rounded p-2 mt-1 space-y-0.5">
                              {rx.medicines.map((m, i) => (
                                <div key={i} className="flex justify-between">
                                  <span>{m.name} {m.dosage ? `· ${m.dosage}` : ''} {m.duration ? `(${m.duration})` : ''}</span>
                                  {rx.type === 'pharmacy' && <span className="text-gray-600">₹{parseFloat(m.total_price || 0).toFixed(2)}</span>}
                                </div>
                              ))}
                            </div>
                          )}
                          {rx.notes && <p className="mt-1 text-gray-700 italic">{rx.notes}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Lab Orders */}
                <TabsContent value="labs" className="mt-3">
                  {wardRoundLabOrders.length === 0 ? (
                    <p className="text-xs text-gray-500 text-center py-4">No lab orders for this admission.</p>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {wardRoundLabOrders.map(o => (
                        <div key={o.id} className="border rounded p-2 text-xs bg-white">
                          <div className="flex justify-between">
                            <span className="font-medium">{o.test_name || o.order_number}</span>
                            <Badge className={o.status === 'completed' ? 'bg-green-100 text-green-800' : o.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'}>{o.status}</Badge>
                          </div>
                          <div className="text-gray-500">{o.order_number} · {o.priority || 'normal'} · {o.created_at ? new Date(o.created_at).toLocaleString() : ''}</div>
                          {o.notes && <p className="mt-1 text-gray-700 italic">{o.notes}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                {/* Nursing notes */}
                <TabsContent value="nursing" className="mt-3">
                  {wardRoundNursingNotes.length === 0 ? (
                    <p className="text-xs text-gray-500 text-center py-4">No nursing notes.</p>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {wardRoundNursingNotes.map(n => (
                        <div key={n.id} className="border rounded p-2 text-xs bg-white">
                          <div className="flex items-center gap-1 mb-1">
                            <Badge className={`text-[10px] px-1 ${n.shift === 'morning' ? 'bg-yellow-100 text-yellow-800' : n.shift === 'afternoon' ? 'bg-orange-100 text-orange-800' : 'bg-indigo-100 text-indigo-800'}`}>{n.shift}</Badge>
                            <Badge variant="outline" className="text-[10px] px-1">{n.note_type}</Badge>
                            <span className="text-gray-400 ml-auto">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
                          </div>
                          <div className="text-gray-500">by {n.nurse_name || 'N/A'}</div>
                          <p className="mt-1 text-gray-700 whitespace-pre-wrap">{n.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Inpatient — Add Prescription dialog */}
      <Dialog open={showInpatientRxDialog} onOpenChange={setShowInpatientRxDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Prescription · {wardRoundAdmission?.patient_name}</DialogTitle></DialogHeader>
          <form onSubmit={handleInpatientRxSubmit} className="space-y-3">
            <div>
              <Label className="text-xs">Notes (optional)</Label>
              <Textarea rows={2} value={inpatientRxForm.notes} onChange={e => setInpatientRxForm(p => ({ ...p, notes: e.target.value }))} placeholder="e.g., After meals, review in 3 days" />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Medicines *</Label>
                <Button type="button" size="sm" variant="outline" onClick={() => setInpatientRxForm(p => ({ ...p, items: [...p.items, { ...RX_BLANK_ITEM }] }))}>
                  <Plus className="h-3 w-3 mr-1" /> Add Row
                </Button>
              </div>
              {inpatientRxForm.items.map((it, idx) => (
                <div key={idx} className="border rounded p-2 space-y-2 bg-gray-50">
                  <div className="flex items-start gap-2">
                    <div className="flex-1">
                      <MedicineLookupInput
                        admissionId={wardRoundAdmission?.id}
                        value={it.medicine_name}
                        medicineId={it.medicine_id}
                        onChange={({ medicine_id, medicine_name }) => setInpatientRxForm(p => {
                          const next = [...p.items];
                          next[idx] = { ...next[idx], medicine_id, medicine_name };
                          return { ...p, items: next };
                        })}
                      />
                    </div>
                    <Button type="button" size="sm" variant="ghost" className="h-9 w-9 p-0" disabled={inpatientRxForm.items.length === 1}
                      onClick={() => setInpatientRxForm(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }))}>
                      <XCircle className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    <div>
                      <Label className="text-[10px] text-gray-500">Dosage *</Label>
                      <Input placeholder="1 tab" value={it.dosage}
                        onChange={e => setInpatientRxForm(p => { const next = [...p.items]; next[idx] = { ...next[idx], dosage: e.target.value }; return { ...p, items: next }; })} />
                    </div>
                    <PrescriptionScheduleFields
                      frequencySchedule={it.frequency_schedule}
                      foodTiming={it.food_timing}
                      onFrequencyChange={(v) => setInpatientRxForm(p => {
                        const next = [...p.items]; next[idx] = { ...next[idx], frequency_schedule: v }; return { ...p, items: next };
                      })}
                      onFoodTimingChange={(v) => setInpatientRxForm(p => {
                        const next = [...p.items]; next[idx] = { ...next[idx], food_timing: v }; return { ...p, items: next };
                      })}
                    />
                    <div>
                      <Label className="text-[10px] text-gray-500">Duration *</Label>
                      <Input placeholder="5 days" value={it.duration}
                        onChange={e => setInpatientRxForm(p => { const next = [...p.items]; next[idx] = { ...next[idx], duration: e.target.value }; return { ...p, items: next }; })} />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Quantity</Label>
                      <Input type="number" min="1" value={it.quantity_prescribed}
                        onChange={e => setInpatientRxForm(p => { const next = [...p.items]; next[idx] = { ...next[idx], quantity_prescribed: e.target.value }; return { ...p, items: next }; })} />
                    </div>
                  </div>
                  <div>
                    <Label className="text-[10px] text-gray-500">Extra instructions (optional)</Label>
                    <Input placeholder="With water, avoid alcohol, etc." value={it.instructions}
                      onChange={e => setInpatientRxForm(p => { const next = [...p.items]; next[idx] = { ...next[idx], instructions: e.target.value }; return { ...p, items: next }; })} />
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-gray-500">Catalog picks use pharmacy Rate-A for inpatient billing. Free-text entries are mapped by pharmacy before dispensing.</p>
            </div>
            <Button type="submit" className="w-full">Create Prescription</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Inpatient — Order Lab Test dialog */}
      <Dialog open={showInpatientLabDialog} onOpenChange={setShowInpatientLabDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Order Lab Test · {wardRoundAdmission?.patient_name}</DialogTitle></DialogHeader>
          <form onSubmit={handleInpatientLabSubmit} className="space-y-3">
            <div>
              <Label className="text-xs">Search</Label>
              <Input placeholder="Filter tests by name…" value={inpatientLabSearch} onChange={e => setInpatientLabSearch(e.target.value)} />
            </div>
            <div className="border rounded max-h-60 overflow-y-auto">
              {inpatientLabAvailableTests.length === 0 ? (
                <p className="text-xs text-gray-500 text-center py-3">No tests available.</p>
              ) : (
                inpatientLabAvailableTests
                  .filter(t => !inpatientLabSearch || (t.name || '').toLowerCase().includes(inpatientLabSearch.toLowerCase()))
                  .map(t => {
                    const checked = inpatientLabForm.test_ids.includes(t.id);
                    return (
                      <label key={t.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 cursor-pointer text-xs border-b last:border-b-0">
                        <input type="checkbox" checked={checked} onChange={() => setInpatientLabForm(p => ({
                          ...p,
                          test_ids: checked ? p.test_ids.filter(id => id !== t.id) : [...p.test_ids, t.id],
                        }))} />
                        <span className="flex-1">{t.name}</span>
                        <span className="text-gray-500">₹{Number(t.price || 0).toFixed(2)}</span>
                      </label>
                    );
                  })
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Priority</Label>
                <Select value={inpatientLabForm.priority} onValueChange={v => setInpatientLabForm(p => ({ ...p, priority: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="stat">STAT</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Notes</Label>
                <Input value={inpatientLabForm.notes} onChange={e => setInpatientLabForm(p => ({ ...p, notes: e.target.value }))} />
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={inpatientLabForm.test_ids.length === 0}>
              Order {inpatientLabForm.test_ids.length} test{inpatientLabForm.test_ids.length === 1 ? '' : 's'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Doctor Visit Dialog for Inpatient */}
      <Dialog open={showDoctorVisitDialog} onOpenChange={setShowDoctorVisitDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Record Doctor Visit - {doctorVisitAdmission?.patient_name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={async (e) => {
            e.preventDefault();
            try {
              await axios.post(`/api/inpatient/admissions/${doctorVisitAdmission.id}/visits`, {
                visit_type: 'doctor_visit',
                visitor_id: user?.id,
                notes: doctorVisitNotes || null,
              });
              toast({ title: 'Success', description: 'Doctor visit recorded' });
              setShowDoctorVisitDialog(false);
              // Refresh the admissions list and, if the manage popup is open, its sections too
              axios.get('/api/inpatient/admissions', { params: { status: 'admitted' } })
                .then(r => {
                  const list = r.data?.items || (Array.isArray(r.data) ? r.data : []);
                  const myAdmissions = list.filter(a =>
                    a.admitting_doctor_id === user.id || a.attending_physician_id === user.id
                  );
                  setDoctorAdmissions(myAdmissions);
                }).catch(() => {});
              if (showManageAdmissionDialog && wardRoundAdmission?.id === doctorVisitAdmission.id) {
                refreshManageAdmission();
              }
            } catch (err) {
              toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to record visit' });
            }
          }} className="space-y-4">
            <div>
              <Label>Visit Notes</Label>
              <Textarea value={doctorVisitNotes} onChange={e => setDoctorVisitNotes(e.target.value)} rows={4} placeholder="Clinical observations, treatment plan, progress notes..." />
            </div>
            <Button type="submit" className="w-full">Record Visit</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* === DIALOGS === */}

      {/* Consultation Dialog */}
      <Dialog open={showConsultationDialog} onOpenChange={setShowConsultationDialog}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Stethoscope className="h-5 w-5" />
              Consultation - {selectedAppointment?.patient_name}
              {activeConsultation && (
                <Badge className="bg-green-100 text-green-800 ml-2">
                  {activeConsultation.consultation_number}
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Chief Complaint *</Label>
              <Textarea
                value={consultationForm.chief_complaint}
                onChange={(e) => setConsultationForm(prev => ({ ...prev, chief_complaint: e.target.value }))}
                placeholder="Patient's primary complaint..."
                rows={2}
              />
            </div>
            <div>
              <Label>Present History</Label>
              <Textarea
                value={consultationForm.present_history}
                onChange={(e) => setConsultationForm(prev => ({ ...prev, present_history: e.target.value }))}
                placeholder="History of present illness, onset, duration, associated symptoms..."
                rows={3}
              />
            </div>
            <div>
              <Label>Examination Findings</Label>
              <Textarea
                value={consultationForm.examination_findings}
                onChange={(e) => setConsultationForm(prev => ({ ...prev, examination_findings: e.target.value }))}
                placeholder="Physical examination findings..."
                rows={3}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Follow-up Date</Label>
                <Input
                  type="date"
                  value={consultationForm.follow_up_date}
                  onChange={(e) => setConsultationForm(prev => ({ ...prev, follow_up_date: e.target.value }))}
                />
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea
                  value={consultationForm.notes}
                  onChange={(e) => setConsultationForm(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="Additional clinical notes..."
                  rows={2}
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-4 border-t">
              <Button variant="outline" size="sm"
                onClick={() => { setShowConsultationDialog(false); setShowVitalsDialog(true); }}>
                <Activity className="h-4 w-4 mr-1" /> Vitals
              </Button>
              <Button variant="outline" size="sm"
                onClick={() => {
                  setShowConsultationDialog(false);
                  // Pre-fill prescription form with existing prescription if available
                  if (createdPrescription?.medicines?.length > 0) {
                    setPrescriptionForm(prev => ({
                      ...prev,
                      diagnosis: createdPrescription.diagnosis || prev.diagnosis,
                      notes: createdPrescription.notes || prev.notes,
                      medications: createdPrescription.medicines.map(m => ({
                        medicine_id: m.medicine_id || '',
                        medicine_name: m.name || '',
                        quantity_prescribed: m.quantity ? parseInt(m.quantity) || 1 : 1,
                        dosage: m.dosage || '',
                        frequency_schedule: m.frequency_schedule || '1-0-0',
                        food_timing: m.food_timing || 'after_food',
                        duration: m.duration || '',
                        instructions: m.instructions || ''
                      }))
                    }));
                  }
                  setShowPrescriptionDialog(true);
                }}>
                <Pill className="h-4 w-4 mr-1" /> Prescribe
              </Button>
              <Button variant="outline" size="sm"
                onClick={() => { setShowConsultationDialog(false); setShowLabOrderDialog(true); }}>
                <TestTube className="h-4 w-4 mr-1" /> Lab Order
              </Button>
              <div className="flex-1" />
              <Button variant="outline" onClick={() => setShowConsultationDialog(false)}>Cancel</Button>
              <Button onClick={handleSaveConsultation} disabled={loading}>
                {activeConsultation ? 'Update Consultation' : 'Create Consultation'}
              </Button>
              {activeConsultation && activeConsultation.status === 'ongoing' && (
                <Button variant="default" className="bg-green-600 hover:bg-green-700"
                  onClick={handleCompleteConsultation} disabled={loading}>
                  <CheckCircle className="h-4 w-4 mr-1" /> Complete
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Patient History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              Patient Visit History
              {patientHistory && (
                <span className="text-sm font-normal text-gray-600 ml-2">
                  - {patientHistory.patient_name}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          {historyLoading ? (
            <div className="text-center py-8">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
              <p className="text-gray-600">Loading history...</p>
            </div>
          ) : patientHistory?.appointments?.length > 0 ? (
            <div className="space-y-3">
              {patientHistory.appointments.map((apt, idx) => (
                <div key={idx} className="border rounded-lg p-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {apt.appointment_date ? new Date(apt.appointment_date).toLocaleDateString() : 'N/A'}
                        </span>
                        <span className="text-sm text-gray-600">
                          {apt.appointment_time ? formatTime(apt.appointment_time) : ''}
                        </span>
                        <Badge className={getStatusColor(apt.status)}>{getStatusLabel(apt.status)}</Badge>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">{apt.doctor_name}</p>
                      {apt.reason && <p className="text-sm text-gray-500">Reason: {apt.reason}</p>}
                      {apt.notes && <p className="text-xs text-gray-400 mt-1">Notes: {apt.notes}</p>}
                    </div>
                    <div className="text-right text-sm">
                      <Badge variant="outline">{apt.appointment_type}</Badge>
                      {apt.consultation_fee > 0 && (
                        <div className="text-gray-500 mt-1">₹{apt.consultation_fee}</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-gray-500 py-8">No visit history found</p>
          )}
        </DialogContent>
      </Dialog>

      {/* Notes Dialog */}
      <Dialog open={showNotesDialog} onOpenChange={setShowNotesDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Appointment Notes - {notesAppointment?.patient_name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              placeholder="Add clinical notes, observations, instructions..."
              rows={5}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowNotesDialog(false)}>Cancel</Button>
              <Button onClick={handleSaveNotes}>Save Notes</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prescription Dialog */}
      <Dialog open={showPrescriptionDialog} onOpenChange={setShowPrescriptionDialog}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Write Prescription - {selectedAppointment?.patient_name}</DialogTitle>
          </DialogHeader>
          <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); submitPrescription(); }}>
            <div>
              <Label htmlFor="diagnosis">Diagnosis</Label>
              <Textarea
                id="diagnosis"
                value={prescriptionForm.diagnosis}
                onChange={(e) => setPrescriptionForm(prev => ({ ...prev, diagnosis: e.target.value }))}
                placeholder="Enter diagnosis..."
              />
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <Label className="text-sm font-semibold">Medications</Label>
              </div>
              <div className="relative border rounded-lg overflow-visible">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b text-left">
                      <th className="px-2 py-2 font-medium text-gray-500 w-8">#</th>
                      <th className="px-2 py-2 font-medium text-gray-500">Medicine Name</th>
                      <th className="px-2 py-2 font-medium text-gray-500 w-20">Dosage</th>
                      <th className="px-2 py-2 font-medium text-gray-500 w-36">Schedule</th>
                      <th className="px-2 py-2 font-medium text-gray-500 w-24">Food</th>
                      <th className="px-2 py-2 font-medium text-gray-500 w-20">Duration</th>
                      <th className="px-2 py-2 font-medium text-gray-500 w-48">Instructions</th>
                      <th className="px-2 py-2 w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {prescriptionForm.medications.map((medication, index) => (
                        <tr key={index} className="border-b last:border-0 hover:bg-gray-50/50">
                          <td className="px-2 py-2 text-gray-400 text-center">{index + 1}</td>
                          <td className="px-2 py-2">
                            <MedicineLookupInput
                              lookupUrl="/api/prescriptions/medicines-lookup"
                              value={medication.medicine_name || ''}
                              medicineId={medication.medicine_id}
                              onChange={({ medicine_id, medicine_name }) => {
                                setPrescriptionForm(prev => ({
                                  ...prev,
                                  medications: prev.medications.map((item, i) => (
                                    i === index ? { ...item, medicine_id, medicine_name } : item
                                  )),
                                }));
                              }}
                              placeholder="Search pharmacy or type medicine"
                              className="[&_input]:h-8 [&_input]:text-sm"
                            />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={medication.dosage}
                              onChange={(e) => updateMedication(index, 'dosage', e.target.value)}
                              placeholder="1 tab" className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            <select value={medication.frequency_schedule || '1-0-0'}
                              onChange={(e) => updateMedication(index, 'frequency_schedule', e.target.value)}
                              className="w-full h-8 text-xs border border-gray-200 rounded px-1">
                              <option value="1-0-0">Morning only</option>
                              <option value="0-1-0">Afternoon only</option>
                              <option value="0-0-1">Night only</option>
                              <option value="1-0-1">Morning & Night</option>
                              <option value="1-1-0">Morning & Afternoon</option>
                              <option value="1-1-1">Three times a day</option>
                              <option value="0-1-1">Afternoon & Night</option>
                            </select>
                          </td>
                          <td className="px-2 py-2">
                            <select value={medication.food_timing || 'after_food'}
                              onChange={(e) => updateMedication(index, 'food_timing', e.target.value)}
                              className="w-full h-8 text-xs border border-gray-200 rounded px-1">
                              <option value="before_food">Before food</option>
                              <option value="after_food">After food</option>
                              <option value="with_food">With food</option>
                              <option value="on_empty_stomach">Empty stomach</option>
                              <option value="anytime">Anytime</option>
                            </select>
                          </td>
                          <td className="px-2 py-2">
                            <Input value={medication.duration}
                              onChange={(e) => updateMedication(index, 'duration', e.target.value)}
                              placeholder="7 days" className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={medication.instructions}
                              onChange={(e) => updateMedication(index, 'instructions', e.target.value)}
                              placeholder="Notes..." className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            {prescriptionForm.medications.length > 1 && (
                              <button type="button" onClick={() => removeMedication(index)}
                                className="text-red-400 hover:text-red-600 text-lg leading-none">×</button>
                            )}
                          </td>
                        </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-3 py-2 bg-gray-50 border-t">
                  <button type="button" onClick={addMedication}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                    + Add Medicine
                  </button>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Follow-up Date</Label>
                <Input
                  type="date"
                  value={prescriptionForm.follow_up_date}
                  onChange={(e) => setPrescriptionForm(prev => ({ ...prev, follow_up_date: e.target.value }))}
                />
              </div>
              <div>
                <Label>Additional Notes</Label>
                <Textarea
                  value={prescriptionForm.notes}
                  onChange={(e) => setPrescriptionForm(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="Additional notes..."
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setShowPrescriptionDialog(false)}>Cancel</Button>
              <Button type="submit" disabled={loading}>Save Prescription</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Lab Order Dialog */}
      <Dialog open={showLabOrderDialog} onOpenChange={(open) => {
        setShowLabOrderDialog(open);
        if (open) {
          fetchAvailableLabTests();
          setSelectedLabTests([]);
          setCustomLabTests([]);
          setCustomLabTestInput('');
          setLabSearchQuery('');
          setLabCategoryFilter('all');
          setLabDuplicateWarning(null);
        }
      }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Order Lab Tests - {selectedAppointment?.patient_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="relative flex-1">
                <Input placeholder="Search tests..." value={labSearchQuery}
                  onChange={(e) => setLabSearchQuery(e.target.value)} className="pl-8" />
                <TestTube className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
              </div>
              <Select value={labCategoryFilter} onValueChange={setLabCategoryFilter}>
                <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Categories" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  {labCategories.map(cat => (
                    <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {(selectedLabTests.length > 0 || customLabTests.length > 0) && (
              <div className="bg-blue-50 p-2 rounded-lg">
                <p className="text-sm text-blue-700 font-medium mb-1">
                  {selectedLabTests.length + customLabTests.length} test(s) selected
                </p>
                <div className="flex flex-wrap gap-1">
                  {selectedLabTests.map(id => {
                    const t = availableLabTests.find(t => t.id === id);
                    return t ? (
                      <Badge key={id} variant="secondary" className="cursor-pointer" onClick={() => toggleLabTestSelection(id)}>
                        {t.name} x
                      </Badge>
                    ) : null;
                  })}
                  {customLabTests.map(name => (
                    <Badge key={name} variant="outline" className="cursor-pointer bg-orange-50 text-orange-700 border-orange-300"
                      onClick={() => removeCustomLabTest(name)}>
                      {name} (custom) x
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div className="border rounded-lg max-h-[300px] overflow-y-auto">
              {filteredLabTests.length === 0 ? (
                <p className="text-center text-gray-500 py-6">No tests available. Ask admin to configure lab tests.</p>
              ) : (
                filteredLabTests.map(test => (
                  <div key={test.id}
                    className={`flex items-center justify-between p-3 border-b last:border-0 cursor-pointer hover:bg-gray-50 ${
                      selectedLabTests.includes(test.id) ? 'bg-blue-50' : ''
                    }`}
                    onClick={() => toggleLabTestSelection(test.id)}>
                    <div>
                      <div className="flex items-center gap-2">
                        <input type="checkbox" checked={selectedLabTests.includes(test.id)} readOnly className="rounded" />
                        <span className="font-medium">{test.name}</span>
                        <Badge variant="outline" className="text-xs">{test.test_code}</Badge>
                      </div>
                      <div className="text-xs text-gray-500 ml-6">
                        {test.category_name} | Rs. {test.cost}
                        {test.sample_type && ` | ${test.sample_type}`}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="border rounded-lg p-3 space-y-2">
              <Label className="text-sm font-medium">Other (test not in list)</Label>
              <div className="flex gap-2">
                <Input value={customLabTestInput}
                  onChange={(e) => setCustomLabTestInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomLabTest(); } }}
                  placeholder="Enter test name and press Enter or Add"
                  className="flex-1" />
                <Button type="button" size="sm" variant="outline" onClick={addCustomLabTest}
                  disabled={!customLabTestInput.trim()}>
                  Add
                </Button>
              </div>
              {customLabTests.length > 0 && (
                <p className="text-xs text-orange-600">
                  Custom tests will be noted for the lab team to process manually.
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Priority</Label>
                <Select value={labOrderPriority} onValueChange={setLabOrderPriority}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="stat">STAT (Emergency)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea value={labOrderNotes} onChange={(e) => setLabOrderNotes(e.target.value)}
                  placeholder="Clinical notes..." rows={2} />
              </div>
            </div>

            {/* Duplicate Warning */}
            {labDuplicateWarning && labDuplicateWarning.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                <p className="text-sm font-semibold text-amber-800">
                  ⚠ These tests were already ordered for this patient today:
                </p>
                <ul className="space-y-1 ml-6">
                  {labDuplicateWarning.map((d, i) => (
                    <li key={i} className="text-sm text-amber-700">
                      <span className="font-medium">{d.test_name}</span>
                      <span className="text-amber-500 text-xs ml-1">(ordered at {d.order_time}, {d.status})</span>
                    </li>
                  ))}
                </ul>
                <div className="flex gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => setLabDuplicateWarning(null)}>Go Back & Edit</Button>
                  <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => { setLabDuplicateWarning(null); handleSubmitLabOrder(true); }}>
                    Proceed Anyway
                  </Button>
                </div>
              </div>
            )}

            <div className={`flex justify-end gap-2 ${labDuplicateWarning ? 'hidden' : ''}`}>
              <Button variant="outline" onClick={() => setShowLabOrderDialog(false)}>Cancel</Button>
              <Button onClick={() => handleSubmitLabOrder(false)}
                disabled={(selectedLabTests.length === 0 && customLabTests.length === 0) || labOrderSubmitting}>
                {labOrderSubmitting ? 'Ordering...' : `Order ${selectedLabTests.length + customLabTests.length} Test(s)`}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Lab Report View Dialog */}
      <Dialog open={showLabReportDialog} onOpenChange={setShowLabReportDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Lab Report - {viewingLabReport?.test_name}</DialogTitle>
          </DialogHeader>
          {viewingLabReport && (
            <div className="space-y-4">
              <div className="text-sm space-y-1">
                <p>Patient: <strong>{viewingLabReport.patient_name}</strong>
                  {viewingLabReport.patient_gender && ` (${viewingLabReport.patient_gender})`}
                  {(viewingLabReport.patient_age_display || viewingLabReport.patient_age) && `, ${viewingLabReport.patient_age_display || `${viewingLabReport.patient_age} yrs`}`}
                </p>
                <p className="text-gray-500">Order: #{viewingLabReport.order_number} | Date: {format(new Date(viewingLabReport.report_date), 'dd MMM yyyy, hh:mm a')}</p>
              </div>

              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="pb-2 pr-3">Parameter</th>
                    <th className="pb-2 pr-3">Result</th>
                    <th className="pb-2 pr-3">Unit</th>
                    <th className="pb-2 pr-3">Reference</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {viewingLabReport.results?.map((r, idx) => (
                    <tr key={idx} className={`border-b ${r.is_abnormal ? 'bg-red-50' : ''}`}>
                      <td className="py-2 pr-3 font-medium">{r.parameter_name}</td>
                      <td className={`py-2 pr-3 ${r.is_abnormal ? 'text-red-600 font-bold' : ''}`}>{r.value}</td>
                      <td className="py-2 pr-3 text-gray-500">{r.unit || '-'}</td>
                      <td className="py-2 pr-3 text-gray-500 text-xs">
                        {r.reference_min != null || r.reference_max != null
                          ? `${r.reference_min ?? '–'} - ${r.reference_max ?? '–'}` : '-'}
                      </td>
                      <td className="py-2">
                        {r.is_abnormal ? (
                          <Badge variant="destructive" className="text-xs">
                            <AlertCircle className="h-3 w-3 mr-1" /> Abnormal
                          </Badge>
                        ) : r.field_type === 'numeric' && (r.reference_min != null || r.reference_max != null) ? (
                          <Badge variant="secondary" className="text-xs">Normal</Badge>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {viewingLabReport.interpretation && (
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm font-medium text-gray-700">Interpretation</p>
                  <p className="text-sm text-gray-600 mt-1">{viewingLabReport.interpretation}</p>
                </div>
              )}

              <div className="flex justify-end gap-2 mt-4">
                <Button variant="outline" onClick={async () => {
                  try {
                    const token = localStorage.getItem('token');
                    const res = await fetch(`/api/lab/reports/${viewingLabReport.id}/download`, {
                      headers: { Authorization: `Bearer ${token}` }
                    });
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `lab_report_${viewingLabReport.order_number}.pdf`;
                    a.click();
                    window.URL.revokeObjectURL(url);
                  } catch (err) {
                    console.error('Failed to download PDF:', err);
                  }
                }}>
                  <Printer className="h-4 w-4 mr-2" /> Download PDF
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Completed Appointments Dialog */}
      <Dialog open={showCompletedAppointments} onOpenChange={setShowCompletedAppointments}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5" />
              Completed Appointments (Last 30 Days)
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {completedAppointments.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No completed appointments found</p>
            ) : (
              completedAppointments.map((appointment) => (
                <Card key={appointment.id} className="border-l-4 border-l-green-500">
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-start">
                      <div className="space-y-2">
                        <div className="font-semibold flex items-center gap-2">
                          <User className="h-4 w-4" />
                          {appointment.patient_name || 'Unknown Patient'}
                        </div>
                        <div className="text-sm text-gray-600 flex items-center gap-2">
                          <Calendar className="h-4 w-4" />
                          {format(new Date(appointment.appointment_date), 'MMMM do, yyyy')}
                          <Clock className="h-4 w-4 ml-2" />
                          {formatTime(appointment.appointment_time)}
                        </div>
                        {appointment.reason && (
                          <div className="text-sm text-gray-600"><strong>Reason:</strong> {appointment.reason}</div>
                        )}
                      </div>
                      <div className="text-right">
                        <Badge className="bg-green-100 text-green-800 mb-2">Completed</Badge>
                        {appointment.consultation_fee > 0 && (
                          <div className="text-sm text-gray-600">Fee: ₹{appointment.consultation_fee}</div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Vitals Dialog */}
      <VitalsForm
        isOpen={showVitalsDialog}
        onClose={() => setShowVitalsDialog(false)}
        selectedPatient={selectedAppointment ? {
          id: selectedAppointment.patient_uuid || selectedAppointment.patient_id,
          first_name: selectedAppointment.patient_name?.split(' ')[0] || '',
          last_name: selectedAppointment.patient_name?.split(' ').slice(1).join(' ') || ''
        } : null}
        userRole="doctor"
        onSave={(vitalsData) => {
          console.log('Vitals saved by doctor:', vitalsData);
        }}
      />

      {/* Success Dialog */}
      <Dialog open={showSuccessDialog} onOpenChange={setShowSuccessDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-green-700">
              <CheckCircle className="h-5 w-5" />
              Prescription Created Successfully!
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="text-center py-4">
              <div className="mb-4">
                <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                  <CheckCircle className="h-8 w-8 text-green-600" />
                </div>
              </div>
              <p className="text-gray-700 mb-2">{successMessage}</p>
              {createdPrescription && (
                <div className="text-sm text-gray-600 space-y-1">
                  <p><strong>Patient:</strong> {createdPrescription.patient_name}</p>
                  <p><strong>Medicines:</strong> {createdPrescription.medicines.length} items</p>
                </div>
              )}
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setShowSuccessDialog(false)} className="flex-1">Continue</Button>
              {createdPrescription && (
                <Button onClick={() => { setShowSuccessDialog(false); showPrintPreview(createdPrescription); }}
                  className="flex-1 flex items-center gap-2">
                  <Eye className="h-4 w-4" /> Preview & Print
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Print Preview Dialog */}
      <Dialog open={showPrintPreviewDialog} onOpenChange={(open) => { if (!open) closePrintPreview(); }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5" />
              Prescription Preview
              {previewPrescription && (
                <span className="text-sm font-normal text-gray-600">- {previewPrescription.prescription_id}</span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden">
            {previewPdfUrl && (
              <iframe src={previewPdfUrl} className="w-full h-[60vh] border rounded-lg" title="Prescription Preview" />
            )}
          </div>
          <div className="pt-4 border-t space-y-3">
            <p className="text-xs text-muted-foreground">
              Letterhead follows Settings → Print Settings.
            </p>
            <div className="flex items-center gap-4">
              <Button variant="outline" size="sm" onClick={refreshPreview}>
                <RefreshCw className="h-3 w-3 mr-1" /> Refresh Preview
              </Button>
            </div>
            <div className="flex justify-between items-center">
              <div className="text-sm text-gray-600">
                {previewPrescription && (
                  <span>
                    Patient: {previewPrescription.patient_name} |
                    Doctor: {previewPrescription.doctor_name} |
                    Date: {new Date(previewPrescription.prescription_date).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={closePrintPreview}>Cancel</Button>
                <Button onClick={printFromPreview}>
                  <Printer className="h-4 w-4 mr-2" /> Print Now
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <DischargeSummaryEditor
        open={showDischargeSummaryEditor && !!wardRoundAdmission}
        onClose={() => setShowDischargeSummaryEditor(false)}
        admissionId={wardRoundAdmission?.id}
        admissionLabel={wardRoundAdmission?.patient_name}
        doctorsList={inpatientDoctorsList}
        readOnly={wardRoundIsDischarged || wardRoundSummaryStatus === 'locked'}
        onSaved={() => {
          refreshManageAdmission();
          if (user) loadDoctorDischargedAdmissions(user);
        }}
      />
    </div>
  );
};

export default DoctorDashboard;
