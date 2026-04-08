import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import { useToast } from '../../hooks/use-toast';
import { printPdfFromUrl } from '../../utils/printPdf';
import {
  Plus, Search, Edit2, Trash2, Bed, Activity, Clock, User, Users,
  FileText, Loader2, X, ChevronLeft, ChevronRight, DollarSign, Stethoscope,
  ClipboardList, LayoutDashboard, Scissors, Shield, Upload, Download, Paperclip
} from 'lucide-react';
import axios from 'axios';

// ============================================================
// Status badge helpers
// ============================================================
const admissionStatusColor = {
  admitted: 'bg-blue-100 text-blue-800',
  discharged: 'bg-green-100 text-green-800',
  transferred: 'bg-yellow-100 text-yellow-800',
};

const otStatusColor = {
  scheduled: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
  postponed: 'bg-orange-100 text-orange-800',
};

const roomTypeLabel = { general: 'General', private: 'Private', icu: 'ICU', emergency: 'Emergency', operation: 'Operation' };

const claimStatusColor = {
  none: 'bg-gray-100 text-gray-800',
  draft: 'bg-yellow-100 text-yellow-800',
  submitted: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
};

const claimStatusLabel = { none: 'No Claim', draft: 'Draft', submitted: 'Submitted', approved: 'Approved', rejected: 'Rejected' };

const InpatientModule = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(false);
  const [confirmState, setConfirmState] = useState({ open: false });

  // Dashboard
  const [dashboardData, setDashboardData] = useState(null);

  // Admissions
  const [admissions, setAdmissions] = useState([]);
  const [admissionSearch, setAdmissionSearch] = useState('');
  const [showAdmissionDialog, setShowAdmissionDialog] = useState(false);
  const [admissionForm, setAdmissionForm] = useState({
    patient_id: '', admitting_doctor_id: '', room_id: '', admission_type: 'elective',
    admission_reason: '', condition_on_admission: 'stable', estimated_stay_days: '',
    admission_notes: '', insurance_provider: '', policy_number: '', claim_reference: '', emergency_contact: '', bed_number: '', bed_id: '',
  });
  const [patientSearchResults, setPatientSearchResults] = useState([]);
  const [patientSearchQuery, setPatientSearchQuery] = useState('');
  const [selectedPatientName, setSelectedPatientName] = useState('');
  const [doctorsList, setDoctorsList] = useState([]);
  const [availableRooms, setAvailableRooms] = useState([]);

  // Activity slide-over
  const [activityAdmission, setActivityAdmission] = useState(null);
  const [activityTab, setActivityTab] = useState('visits');
  const [visits, setVisits] = useState([]);
  const [billData, setBillData] = useState(null);
  const [showVisitDialog, setShowVisitDialog] = useState(false);
  const [visitForm, setVisitForm] = useState({ visit_type: 'doctor_visit', visitor_id: '', notes: '' });
  const [rateConfig, setRateConfig] = useState(null);
  const [admissionMedications, setAdmissionMedications] = useState([]);
  const [admissionLabOrders, setAdmissionLabOrders] = useState([]);
  const [availableLabTests, setAvailableLabTests] = useState([]);
  const [showLabOrderDialog, setShowLabOrderDialog] = useState(false);
  const [labOrderForm, setLabOrderForm] = useState({ test_ids: [], priority: 'normal', notes: '' });
  const [labTestSearch, setLabTestSearch] = useState('');

  // Rooms
  const [rooms, setRooms] = useState([]);
  const [showRoomDialog, setShowRoomDialog] = useState(false);
  const [editingRoom, setEditingRoom] = useState(null);
  const [roomForm, setRoomForm] = useState({
    room_number: '', room_type: 'general', floor: '', department: '',
    bed_count: 1, room_charge_per_day: '',  amenities: '',
  });
  const [rateForm, setRateForm] = useState({ doctor_visit_rate: 0, nurse_visit_rate: 0, procedure_rate: 0 });

  // Bed Management
  const [selectedRoomForBeds, setSelectedRoomForBeds] = useState(null);
  const [roomBeds, setRoomBeds] = useState([]);
  const [newBedLabel, setNewBedLabel] = useState('');
  const [showBedManager, setShowBedManager] = useState(false);
  const [admissionBeds, setAdmissionBeds] = useState([]);  // beds for selected room in admission form
  const [admissionDocs, setAdmissionDocs] = useState([]);
  const [docUploading, setDocUploading] = useState(false);
  const [nursingNotes, setNursingNotes] = useState([]);
  const [showNursingNoteDialog, setShowNursingNoteDialog] = useState(false);
  const [nursingNoteForm, setNursingNoteForm] = useState({ shift: 'morning', note_type: 'general', content: '' });
  const [editingNursingNote, setEditingNursingNote] = useState(null);
  const [nursingShiftFilter, setNursingShiftFilter] = useState('all');

  // Pagination
  const PAGE_SIZE = 50;
  const [admissionsPage, setAdmissionsPage] = useState(0);
  const [admissionsTotal, setAdmissionsTotal] = useState(0);
  const [dischargePage, setDischargePage] = useState(0);
  const [dischargeTotal, setDischargeTotal] = useState(0);

  // Discharge history
  const [dischargeSearch, setDischargeSearch] = useState('');
  const [dischargedAdmissions, setDischargedAdmissions] = useState([]);
  const [showDischargeDialog, setShowDischargeDialog] = useState(false);
  const [dischargeAdmission, setDischargeAdmission] = useState(null);
  const [dischargeForm, setDischargeForm] = useState({
    discharge_type: 'normal', condition_on_discharge: 'stable', discharge_summary: '',
    diagnosis_on_discharge: '', treatment_given: '', medications_prescribed: '',
    follow_up_instructions: '', follow_up_date: '', diet_instructions: '', activity_restrictions: '',
  });

  // OT Schedule
  const [otSchedules, setOtSchedules] = useState([]);
  const [showOTDialog, setShowOTDialog] = useState(false);
  const [otForm, setOtForm] = useState({
    patient_id: '', surgeon_id: '', anaesthetist_id: '', ot_room_number: '',
    procedure_name: '', scheduled_date: '', estimated_duration_minutes: '', pre_op_notes: '', admission_id: '',
  });

  // ============================================================
  // Data fetching
  // ============================================================
  const fetchDashboard = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/dashboard');
      setDashboardData(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchAdmissions = useCallback(async (status = 'admitted', page = 0) => {
    try {
      const res = await axios.get('/api/inpatient/admissions', {
        params: { status, skip: page * PAGE_SIZE, limit: PAGE_SIZE }
      });
      const { items, total } = res.data;
      if (status === 'admitted') {
        setAdmissions(items);
        setAdmissionsTotal(total);
      } else {
        setDischargedAdmissions(items);
        setDischargeTotal(total);
      }
    } catch { /* silent */ }
  }, []);

  const fetchRooms = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/rooms');
      setRooms(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchRateConfig = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/rate-config');
      setRateConfig(res.data);
      setRateForm({ doctor_visit_rate: res.data.doctor_visit_rate, nurse_visit_rate: res.data.nurse_visit_rate, procedure_rate: res.data.procedure_rate });
    } catch { /* silent */ }
  }, []);

  const fetchDoctors = useCallback(async () => {
    try {
      const res = await axios.get('/api/admin/users');
      const docs = (res.data || []).filter(u => (u.role_names || [u.role?.name]).some(r => r === 'doctor'));
      setDoctorsList(docs);
    } catch { /* silent */ }
  }, []);

  const fetchAvailableRooms = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/rooms', { params: { available_only: true } });
      setAvailableRooms(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchVisits = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/visits`);
      setVisits(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchBill = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/bill`);
      setBillData(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchMedications = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/prescriptions`);
      setAdmissionMedications(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchLabOrders = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/lab-orders`);
      setAdmissionLabOrders(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchAvailableLabTests = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/lab-tests-available`);
      setAvailableLabTests(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchOTSchedules = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/ot');
      setOtSchedules(res.data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchDashboard();
    fetchDoctors();
  }, [fetchDashboard, fetchDoctors]);

  useEffect(() => {
    if (activeTab === 'admissions') { fetchAdmissions('admitted', admissionsPage); fetchAvailableRooms(); }
    if (activeTab === 'rooms') { fetchRooms(); fetchRateConfig(); }
    if (activeTab === 'discharge') fetchAdmissions('discharged', dischargePage);
    if (activeTab === 'ot') fetchOTSchedules();
    if (activeTab === 'dashboard') fetchDashboard();
  }, [activeTab, admissionsPage, dischargePage, fetchAdmissions, fetchRooms, fetchRateConfig, fetchDashboard, fetchAvailableRooms, fetchOTSchedules]);

  // ============================================================
  // Patient search typeahead
  // ============================================================
  useEffect(() => {
    if (patientSearchQuery.length < 2) { setPatientSearchResults([]); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await axios.get('/api/patients', { params: { search: patientSearchQuery } });
        setPatientSearchResults(res.data.patients || res.data || []);
      } catch { setPatientSearchResults([]); }
    }, 300);
    return () => clearTimeout(timer);
  }, [patientSearchQuery]);

  // ============================================================
  // Handlers
  // ============================================================

  // Admission
  const handleCreateAdmission = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...admissionForm,
        patient_id: parseInt(admissionForm.patient_id),
        admitting_doctor_id: parseInt(admissionForm.admitting_doctor_id),
        room_id: parseInt(admissionForm.room_id),
        estimated_stay_days: admissionForm.estimated_stay_days ? parseInt(admissionForm.estimated_stay_days) : null,
        bed_id: admissionForm.bed_id ? parseInt(admissionForm.bed_id) : null,
      };
      await axios.post('/api/inpatient/admissions', payload);
      toast({ title: 'Success', description: 'Patient admitted successfully' });
      setShowAdmissionDialog(false);
      resetAdmissionForm();
      fetchAdmissions('admitted');
      fetchDashboard();
      fetchAvailableRooms();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create admission';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const resetAdmissionForm = () => {
    setAdmissionForm({ patient_id: '', admitting_doctor_id: '', room_id: '', admission_type: 'elective',
      admission_reason: '', condition_on_admission: 'stable', estimated_stay_days: '',
      admission_notes: '', insurance_provider: '', policy_number: '', claim_reference: '', emergency_contact: '', bed_number: '', bed_id: '' });
    setSelectedPatientName('');
    setPatientSearchQuery('');
    setPatientSearchResults([]);
  };

  // Activity
  const openActivity = (admission) => {
    setActivityAdmission(admission);
    setActivityTab('visits');
    fetchVisits(admission.id);
    fetchBill(admission.id);
    fetchMedications(admission.id);
    fetchLabOrders(admission.id);
    fetchAdmissionDocs(admission.id);
    fetchNursingNotes(admission.id);
  };

  // Visit
  const handleCreateVisit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/visits`, {
        visit_type: visitForm.visit_type,
        visitor_id: parseInt(visitForm.visitor_id),
        notes: visitForm.notes || null,
      });
      toast({ title: 'Success', description: 'Visit recorded' });
      setShowVisitDialog(false);
      setVisitForm({ visit_type: 'doctor_visit', visitor_id: '', notes: '' });
      fetchVisits(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record visit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteVisit = async (visitId) => {
    try {
      await axios.delete(`/api/inpatient/visits/${visitId}`);
      toast({ title: 'Success', description: 'Visit deleted' });
      fetchVisits(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete' });
    }
  };

  // Lab Order
  const handleCreateLabOrder = async (e) => {
    e.preventDefault();
    if (!labOrderForm.test_ids.length) {
      toast({ variant: 'destructive', title: 'Error', description: 'Select at least one lab test' });
      return;
    }
    setLoading(true);
    try {
      await axios.post('/api/lab/orders', {
        patient_id: activityAdmission.patient_id,
        admission_id: activityAdmission.id,
        test_ids: labOrderForm.test_ids,
        priority: labOrderForm.priority,
        notes: labOrderForm.notes || null,
        force: false,
      });
      toast({ title: 'Success', description: 'Lab orders created' });
      setShowLabOrderDialog(false);
      setLabOrderForm({ test_ids: [], priority: 'normal', notes: '' });
      setLabTestSearch('');
      fetchLabOrders(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.message === 'Duplicate orders found') {
        const dupes = detail.duplicates.map(d => d.test_name).join(', ');
        toast({ variant: 'destructive', title: 'Duplicate Orders', description: `Already ordered today: ${dupes}. Remove them from selection or force-submit.` });
      } else {
        const msg = typeof detail === 'string' ? detail : 'Failed to create lab orders';
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } finally { setLoading(false); }
  };

  const toggleLabTest = (testId) => {
    setLabOrderForm(prev => ({
      ...prev,
      test_ids: prev.test_ids.includes(testId)
        ? prev.test_ids.filter(id => id !== testId)
        : [...prev.test_ids, testId],
    }));
  };

  // Finalize bill
  const handleFinalizeBill = async () => {
    if (!activityAdmission) return;
    setLoading(true);
    try {
      const res = await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/bill/finalize`);
      toast({ title: 'Success', description: `Bill ${res.data.bill_number} finalized` });
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to finalize bill' });
    } finally { setLoading(false); }
  };

  // Insurance claim status update
  const handleClaimStatusUpdate = async (admissionId, data) => {
    setLoading(true);
    try {
      const res = await axios.put(`/api/inpatient/admissions/${admissionId}/claim-status`, data);
      toast({ title: 'Success', description: `Claim status updated to ${data.claim_status}` });
      // Update activityAdmission in place
      setActivityAdmission(prev => prev ? { ...prev, ...res.data } : prev);
      // Refresh admissions list
      fetchAdmissions();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Failed to update claim status' });
    } finally { setLoading(false); }
  };

  // Discharge
  const openDischargeDialog = async (admission) => {
    setDischargeAdmission(admission);
    let medsText = '';
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admission.id}/prescriptions`);
      if (res.data && res.data.length > 0) {
        const lines = [];
        for (const rx of res.data) {
          const meds = rx.medicines || [];
          for (const med of meds) {
            const parts = [med.name];
            if (med.dosage) parts.push(med.dosage);
            if (med.duration) parts.push(`for ${med.duration}`);
            if (med.instructions) parts.push(`(${med.instructions})`);
            if (med.quantity) parts.push(`- Qty: ${med.quantity}`);
            lines.push(parts.join(' '));
          }
        }
        medsText = lines.join('\n');
      }
    } catch { /* silent */ }
    setDischargeForm({ discharge_type: 'normal', condition_on_discharge: 'stable', discharge_summary: '',
      diagnosis_on_discharge: '', treatment_given: '', medications_prescribed: medsText,
      follow_up_instructions: '', follow_up_date: '', diet_instructions: '', activity_restrictions: '' });
    setShowDischargeDialog(true);
  };

  const handleDischarge = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...dischargeForm };
      if (payload.follow_up_date) payload.follow_up_date = new Date(payload.follow_up_date).toISOString();
      else delete payload.follow_up_date;
      await axios.post(`/api/inpatient/admissions/${dischargeAdmission.id}/discharge`, payload);
      toast({ title: 'Success', description: 'Patient discharged successfully' });
      setShowDischargeDialog(false);
      setDischargeAdmission(null);
      fetchAdmissions('admitted');
      fetchDashboard();
      if (activityAdmission?.id === dischargeAdmission.id) setActivityAdmission(null);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to discharge patient';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Room CRUD
  const handleSaveRoom = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...roomForm, bed_count: parseInt(roomForm.bed_count), room_charge_per_day: parseFloat(roomForm.room_charge_per_day) };
      if (editingRoom) {
        await axios.put(`/api/inpatient/rooms/${editingRoom.id}`, payload);
        toast({ title: 'Success', description: 'Room updated' });
      } else {
        await axios.post('/api/inpatient/rooms', payload);
        toast({ title: 'Success', description: 'Room created' });
      }
      setShowRoomDialog(false);
      setEditingRoom(null);
      resetRoomForm();
      fetchRooms();
      fetchDashboard();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to save room' });
    } finally { setLoading(false); }
  };

  const resetRoomForm = () => setRoomForm({ room_number: '', room_type: 'general', floor: '', department: '', bed_count: 1, room_charge_per_day: '', amenities: '' });

  const handleEditRoom = (room) => {
    setEditingRoom(room);
    setRoomForm({ room_number: room.room_number, room_type: room.room_type, floor: room.floor || '', department: room.department || '',
      bed_count: room.bed_count, room_charge_per_day: room.room_charge_per_day, amenities: room.amenities || '' });
    setShowRoomDialog(true);
  };

  const handleDeleteRoom = async (roomId) => {
    try {
      await axios.delete(`/api/inpatient/rooms/${roomId}`);
      toast({ title: 'Success', description: 'Room deactivated' });
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete room' });
    }
  };

  const handleSaveRateConfig = async () => {
    setLoading(true);
    try {
      await axios.put('/api/inpatient/rate-config', {
        doctor_visit_rate: parseFloat(rateForm.doctor_visit_rate),
        nurse_visit_rate: parseFloat(rateForm.nurse_visit_rate),
        procedure_rate: parseFloat(rateForm.procedure_rate),
      });
      toast({ title: 'Success', description: 'Rate configuration updated' });
      fetchRateConfig();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update rates' });
    } finally { setLoading(false); }
  };

  // Bed Management
  const fetchBeds = async (roomId) => {
    try {
      const res = await axios.get(`/api/inpatient/rooms/${roomId}/beds`);
      setRoomBeds(res.data);
    } catch { setRoomBeds([]); }
  };

  const openBedManager = (room) => {
    setSelectedRoomForBeds(room);
    fetchBeds(room.id);
    setNewBedLabel('');
    setShowBedManager(true);
  };

  const handleAddBed = async () => {
    if (!newBedLabel.trim() || !selectedRoomForBeds) return;
    try {
      await axios.post(`/api/inpatient/rooms/${selectedRoomForBeds.id}/beds`, { bed_label: newBedLabel.trim() });
      setNewBedLabel('');
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
      toast({ title: 'Success', description: 'Bed added' });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to add bed' });
    }
  };

  const handleUpdateBedStatus = async (bedId, newStatus) => {
    try {
      await axios.patch(`/api/inpatient/beds/${bedId}`, { status: newStatus });
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to update bed' });
    }
  };

  const handleDeleteBed = async (bedId) => {
    try {
      await axios.delete(`/api/inpatient/beds/${bedId}`);
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
      toast({ title: 'Success', description: 'Bed removed' });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete bed' });
    }
  };

  // Admission Documents
  const fetchAdmissionDocs = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/documents`);
      setAdmissionDocs(res.data);
    } catch { setAdmissionDocs([]); }
  };

  const handleDocUpload = async (admissionId, file, docType, docName, notes) => {
    setDocUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);
      formData.append('document_name', docName || file.name);
      if (notes) formData.append('notes', notes);
      await axios.post(`/api/inpatient/admissions/${admissionId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast({ title: 'Success', description: 'Document uploaded' });
      fetchAdmissionDocs(admissionId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Upload failed' });
    } finally { setDocUploading(false); }
  };

  const handleDocDelete = async (docId) => {
    try {
      await axios.delete(`/api/inpatient/documents/${docId}`);
      toast({ title: 'Success', description: 'Document deleted' });
      if (activityAdmission) fetchAdmissionDocs(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete document' });
    }
  };

  // Nursing Notes
  const fetchNursingNotes = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/nursing-notes`);
      setNursingNotes(res.data);
    } catch { setNursingNotes([]); }
  };

  const handleCreateNursingNote = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (editingNursingNote) {
        await axios.put(`/api/inpatient/nursing-notes/${editingNursingNote.id}`, nursingNoteForm);
        toast({ title: 'Success', description: 'Nursing note updated' });
      } else {
        await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/nursing-notes`, nursingNoteForm);
        toast({ title: 'Success', description: 'Nursing note added' });
      }
      setShowNursingNoteDialog(false);
      setEditingNursingNote(null);
      setNursingNoteForm({ shift: 'morning', note_type: 'general', content: '' });
      fetchNursingNotes(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to save nursing note';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteNursingNote = async (noteId) => {
    try {
      await axios.delete(`/api/inpatient/nursing-notes/${noteId}`);
      toast({ title: 'Success', description: 'Nursing note deleted' });
      fetchNursingNotes(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete nursing note' });
    }
  };

  // OT Schedule
  const handleCreateOT = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        patient_id: parseInt(otForm.patient_id),
        surgeon_id: parseInt(otForm.surgeon_id),
        anaesthetist_id: otForm.anaesthetist_id ? parseInt(otForm.anaesthetist_id) : null,
        admission_id: otForm.admission_id ? parseInt(otForm.admission_id) : null,
        ot_room_number: otForm.ot_room_number,
        procedure_name: otForm.procedure_name,
        scheduled_date: new Date(otForm.scheduled_date).toISOString(),
        estimated_duration_minutes: otForm.estimated_duration_minutes ? parseInt(otForm.estimated_duration_minutes) : null,
        pre_op_notes: otForm.pre_op_notes || null,
      };
      await axios.post('/api/inpatient/ot', payload);
      toast({ title: 'Success', description: 'OT scheduled successfully' });
      setShowOTDialog(false);
      setOtForm({ patient_id: '', surgeon_id: '', anaesthetist_id: '', ot_room_number: '', procedure_name: '', scheduled_date: '', estimated_duration_minutes: '', pre_op_notes: '', admission_id: '' });
      fetchOTSchedules();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to schedule OT' });
    } finally { setLoading(false); }
  };

  const handleUpdateOTStatus = async (otId, newStatus) => {
    try {
      await axios.patch(`/api/inpatient/ot/${otId}/status`, null, { params: { status: newStatus } });
      toast({ title: 'Success', description: `OT status updated to ${newStatus}` });
      fetchOTSchedules();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update status' });
    }
  };

  // PDF
  const handlePrintDischargePdf = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/discharge/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate discharge PDF' });
    }
  };

  const handlePrintBillPdf = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/bill/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate bill PDF' });
    }
  };

  // Filtered admissions
  const filteredAdmissions = admissions.filter(a => {
    if (!admissionSearch) return true;
    const q = admissionSearch.toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(q) ||
           (a.admission_number || '').toLowerCase().includes(q) ||
           (a.room_number || '').toLowerCase().includes(q);
  });

  const filteredDischarged = dischargedAdmissions.filter(a => {
    if (!dischargeSearch) return true;
    const q = dischargeSearch.toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(q) ||
           (a.admission_number || '').toLowerCase().includes(q);
  });

  const daysSince = (dateStr) => {
    if (!dateStr) return 0;
    return Math.max(1, Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000));
  };

  // ============================================================
  // RENDER
  // ============================================================
  const sidebarItems = [
    { key: 'dashboard', label: 'Ward Overview', icon: LayoutDashboard },
    { key: 'admissions', label: 'Active Admissions', icon: Users },
    { key: 'discharge', label: 'Discharge History', icon: FileText },
    { key: 'ot', label: 'OT Schedule', icon: Scissors },
    { key: 'rooms', label: 'Room Management', icon: Bed },
  ];

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* ============ LEFT SIDEBAR ============ */}
      <aside className="w-56 bg-white border-r shrink-0 flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-lg font-bold text-gray-900">Inpatient</h1>
          <p className="text-xs text-gray-500">Management</p>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {sidebarItems.map(item => (
            <button
              key={item.key}
              onClick={() => { setActiveTab(item.key); if (item.key !== 'admissions') setActivityAdmission(null); }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                activeTab === item.key
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </button>
          ))}
        </nav>
        {dashboardData && (
          <div className="p-4 border-t space-y-2 text-xs">
            <div className="flex justify-between text-gray-500">
              <span>Beds</span>
              <span className="font-medium text-gray-900">{dashboardData.occupied}/{dashboardData.total_beds}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${dashboardData.total_beds > 0 ? (dashboardData.occupied / dashboardData.total_beds * 100) : 0}%` }} />
            </div>
            <div className="flex justify-between text-gray-500">
              <span>Active</span>
              <span className="font-medium text-gray-900">{dashboardData.active_admissions}</span>
            </div>
          </div>
        )}
      </aside>

      {/* ============ MAIN CONTENT ============ */}
      <div className="flex-1 overflow-hidden flex flex-col min-w-0">
        {/* Quick Actions Bar */}
        <div className="border-b bg-white px-6 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => { resetAdmissionForm(); fetchAvailableRooms(); setShowAdmissionDialog(true); }}>
              <Plus className="h-4 w-4 mr-1" /> Admit Patient
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowOTDialog(true)}>
              <Scissors className="h-4 w-4 mr-1" /> Schedule OT
            </Button>
            {activityAdmission && (
              <Button size="sm" variant="outline" onClick={() => { setVisitForm({ visit_type: 'doctor_visit', visitor_id: '', notes: '' }); setShowVisitDialog(true); }}>
                <Stethoscope className="h-4 w-4 mr-1" /> New Visit
              </Button>
            )}
          </div>
          {activityAdmission && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">Patient:</span>
              <span className="font-medium">{activityAdmission.patient_name}</span>
              <Badge className={admissionStatusColor[activityAdmission.status] || ''}>{activityAdmission.status}</Badge>
              <Button variant="ghost" size="sm" onClick={() => setActivityAdmission(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden">

          {/* ============ WARD OVERVIEW ============ */}
          {activeTab === 'dashboard' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          {dashboardData ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Total Beds</p>
                        <p className="text-2xl font-bold">{dashboardData.total_beds}</p>
                      </div>
                      <Bed className="h-8 w-8 text-blue-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Occupied</p>
                        <p className="text-2xl font-bold text-orange-600">{dashboardData.occupied}</p>
                      </div>
                      <Activity className="h-8 w-8 text-orange-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Available</p>
                        <p className="text-2xl font-bold text-green-600">{dashboardData.available}</p>
                      </div>
                      <Bed className="h-8 w-8 text-green-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Today Admissions</p>
                        <p className="text-2xl font-bold">{dashboardData.today_admissions}</p>
                      </div>
                      <Plus className="h-8 w-8 text-purple-500" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Active Admissions</p>
                    <p className="text-2xl font-bold">{dashboardData.active_admissions}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Pending Discharges</p>
                    <p className="text-2xl font-bold text-yellow-600">{dashboardData.pending_discharges}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Avg Stay (days)</p>
                    <p className="text-2xl font-bold">{dashboardData.avg_stay_days}</p>
                  </CardContent>
                </Card>
              </div>

              {/* By Type breakdown */}
              {dashboardData.by_type && Object.keys(dashboardData.by_type).length > 0 && (
                <Card>
                  <CardHeader><CardTitle className="text-lg">Bed Occupancy by Type</CardTitle></CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {Object.entries(dashboardData.by_type).map(([type, data]) => (
                        <div key={type} className="border rounded-lg p-3 text-center">
                          <p className="font-semibold text-sm">{roomTypeLabel[type] || type}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            {data.occupied}/{data.total} occupied
                          </p>
                          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                            <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${data.total > 0 ? (data.occupied / data.total * 100) : 0}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
            </div>
          )}
          </div>
          )}

          {/* ============ ACTIVE ADMISSIONS (split view) ============ */}
          {activeTab === 'admissions' && (
            <div className="flex h-full">
              {/* Left: Admissions list */}
              <div className={`${activityAdmission ? 'w-1/2 border-r' : 'w-full'} overflow-y-auto p-6 transition-all space-y-4`}>
                <div className="relative max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input placeholder="Search by name, ID, room..." value={admissionSearch} onChange={e => setAdmissionSearch(e.target.value)} className="pl-10" />
                </div>

                {filteredAdmissions.length === 0 ? (
                  <Card><CardContent className="py-12 text-center text-gray-500">No active admissions found.</CardContent></Card>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 text-sm">Patient</th>
                          <th className="text-left py-2 text-sm">Room / Bed</th>
                          {!activityAdmission && <th className="text-left py-2 text-sm">Doctor</th>}
                          <th className="text-left py-2 text-sm">Admitted</th>
                          <th className="text-left py-2 text-sm">Days</th>
                          <th className="text-left py-2 text-sm">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredAdmissions.map(adm => (
                          <tr key={adm.id} className={`border-b cursor-pointer transition-colors ${activityAdmission?.id === adm.id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                              onClick={() => openActivity(adm)}>
                            <td className="py-2">
                              <div className="flex items-center gap-1">
                                <span className="font-medium text-sm">{adm.patient_name || 'N/A'}</span>
                                {adm.claim_status && adm.claim_status !== 'none' && (
                                  <Shield className="h-3 w-3 text-blue-500" title={`Claim: ${claimStatusLabel[adm.claim_status]}`} />
                                )}
                              </div>
                              <div className="text-xs text-gray-500">{adm.admission_number}</div>
                            </td>
                            <td className="py-2 text-sm">{adm.room_number} {(adm.bed_label || adm.bed_number) ? `/ ${adm.bed_label || adm.bed_number}` : ''}<br /><span className="text-xs text-gray-500">{roomTypeLabel[adm.room_type] || adm.room_type}</span></td>
                            {!activityAdmission && <td className="py-2 text-sm">{adm.doctor_name || 'N/A'}</td>}
                            <td className="py-2 text-sm">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : ''}</td>
                            <td className="py-2 text-sm">{daysSince(adm.admission_date)}</td>
                            <td className="py-2">
                              <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                {adm.status === 'admitted' && (
                                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => openDischargeDialog(adm)} title="Discharge">
                                    <ChevronRight className="h-4 w-4" />
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {admissionsTotal > PAGE_SIZE && (
                      <div className="flex items-center justify-between pt-4 border-t mt-2">
                        <span className="text-sm text-gray-500">
                          Showing {admissionsPage * PAGE_SIZE + 1}–{Math.min((admissionsPage + 1) * PAGE_SIZE, admissionsTotal)} of {admissionsTotal}
                        </span>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" disabled={admissionsPage === 0}
                            onClick={() => setAdmissionsPage(p => p - 1)}>
                            <ChevronLeft className="h-4 w-4 mr-1" /> Prev
                          </Button>
                          <Button variant="outline" size="sm" disabled={(admissionsPage + 1) * PAGE_SIZE >= admissionsTotal}
                            onClick={() => setAdmissionsPage(p => p + 1)}>
                            Next <ChevronRight className="h-4 w-4 ml-1" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Right: Patient detail (inline) */}
              {activityAdmission && (
                <div className="w-1/2 overflow-y-auto flex flex-col">
                  <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between z-10">
                    <div>
                      <h2 className="font-semibold">{activityAdmission.patient_name}</h2>
                      <p className="text-xs text-gray-500">{activityAdmission.admission_number} &bull; {roomTypeLabel[activityAdmission.room_type] || activityAdmission.room_type} - {activityAdmission.room_number} &bull; Dr. {activityAdmission.doctor_name || 'N/A'}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {activityAdmission.status === 'admitted' && (
                        <Button size="sm" variant="outline" className="text-red-600" onClick={() => openDischargeDialog(activityAdmission)}>Discharge</Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => setActivityAdmission(null)}><X className="h-4 w-4" /></Button>
                    </div>
                  </div>

                  <div className="p-4 flex-1">
                    <Tabs value={activityTab} onValueChange={setActivityTab}>
                      <TabsList className="grid w-full grid-cols-7">
                        <TabsTrigger value="visits">Visits</TabsTrigger>
                        <TabsTrigger value="nursing">Nursing</TabsTrigger>
                        <TabsTrigger value="lab">Lab</TabsTrigger>
                        <TabsTrigger value="medications">Meds</TabsTrigger>
                        <TabsTrigger value="bill">Bill</TabsTrigger>
                        <TabsTrigger value="insurance">Insurance</TabsTrigger>
                        <TabsTrigger value="docs">Docs</TabsTrigger>
                      </TabsList>

                      {/* Visits sub-tab */}
                      <TabsContent value="visits" className="space-y-3 mt-3">
                        <Button size="sm" onClick={() => { setVisitForm({ visit_type: 'doctor_visit', visitor_id: '', notes: '' }); setShowVisitDialog(true); }}>
                          <Plus className="h-4 w-4 mr-1" /> Add Visit
                        </Button>
                        {visits.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No visits recorded yet.</p>
                        ) : (
                          <div className="space-y-2">
                            {visits.map(v => (
                              <div key={v.id} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="font-medium">{v.visit_type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                                    <span className="text-gray-500 ml-2">by {v.visitor_name || 'N/A'}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-gray-600">₹{parseFloat(v.charge_amount || 0).toFixed(2)}</span>
                                    {v.billed ? (
                                      <Badge className="bg-green-100 text-green-800 text-xs">Billed</Badge>
                                    ) : (
                                      <Button variant="ghost" size="sm" className="text-red-500 h-6 w-6 p-0"
                                        onClick={() => setConfirmState({ open: true, title: 'Delete Visit', message: 'Delete this visit?',
                                          onConfirm: () => { setConfirmState({ open: false }); handleDeleteVisit(v.id); } })}>
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    )}
                                  </div>
                                </div>
                                <p className="text-xs text-gray-400 mt-1">{v.visit_datetime ? new Date(v.visit_datetime).toLocaleString() : ''}</p>
                                {v.notes && <p className="text-xs text-gray-600 mt-1">{v.notes}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Nursing Notes sub-tab */}
                      <TabsContent value="nursing" className="space-y-3 mt-3">
                        <div className="flex items-center gap-2">
                          <Button size="sm" onClick={() => {
                            setEditingNursingNote(null);
                            setNursingNoteForm({ shift: 'morning', note_type: 'general', content: '' });
                            setShowNursingNoteDialog(true);
                          }}>
                            <Plus className="h-4 w-4 mr-1" /> Add Note
                          </Button>
                          <Select value={nursingShiftFilter} onValueChange={setNursingShiftFilter}>
                            <SelectTrigger className="w-[140px] h-8 text-xs">
                              <SelectValue placeholder="Filter shift" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All Shifts</SelectItem>
                              <SelectItem value="morning">Morning</SelectItem>
                              <SelectItem value="afternoon">Afternoon</SelectItem>
                              <SelectItem value="night">Night</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        {(() => {
                          const filtered = nursingShiftFilter === 'all' ? nursingNotes : nursingNotes.filter(n => n.shift === nursingShiftFilter);
                          return filtered.length === 0 ? (
                            <p className="text-sm text-gray-500 text-center py-4">No nursing notes recorded yet.</p>
                          ) : (
                            <div className="space-y-2">
                              {filtered.map(n => (
                                <div key={n.id} className="border rounded-lg p-3 text-sm">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <Badge className={n.shift === 'morning' ? 'bg-yellow-100 text-yellow-800' : n.shift === 'afternoon' ? 'bg-orange-100 text-orange-800' : 'bg-indigo-100 text-indigo-800'}>
                                        {n.shift.charAt(0).toUpperCase() + n.shift.slice(1)}
                                      </Badge>
                                      <Badge variant="outline">{n.note_type.charAt(0).toUpperCase() + n.note_type.slice(1)}</Badge>
                                      <span className="text-gray-500 text-xs">by {n.nurse_name || 'N/A'}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => {
                                        setEditingNursingNote(n);
                                        setNursingNoteForm({ shift: n.shift, note_type: n.note_type, content: n.content });
                                        setShowNursingNoteDialog(true);
                                      }}>
                                        <Edit2 className="h-3 w-3" />
                                      </Button>
                                      <Button variant="ghost" size="sm" className="text-red-500 h-6 w-6 p-0"
                                        onClick={() => setConfirmState({ open: true, title: 'Delete Note', message: 'Delete this nursing note?',
                                          onConfirm: () => { setConfirmState({ open: false }); handleDeleteNursingNote(n.id); } })}>
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </div>
                                  <p className="text-xs text-gray-400 mt-1">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</p>
                                  <p className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{n.content}</p>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                      </TabsContent>

                      {/* Lab Orders sub-tab */}
                      <TabsContent value="lab" className="space-y-3 mt-3">
                        <Button size="sm" onClick={() => { setLabOrderForm({ test_ids: [], priority: 'normal', notes: '' }); setLabTestSearch(''); fetchAvailableLabTests(activityAdmission.id); setShowLabOrderDialog(true); }}>
                          <Plus className="h-4 w-4 mr-1" /> Order Lab Tests
                        </Button>
                        {admissionLabOrders.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No lab orders for this admission.</p>
                        ) : (
                          <div className="space-y-2">
                            {admissionLabOrders.map(order => (
                              <div key={order.id} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="font-medium">{order.test_name}</span>
                                    {order.test_code && <span className="text-gray-400 ml-1 text-xs">({order.test_code})</span>}
                                  </div>
                                  <Badge className={
                                    order.status === 'completed' ? 'bg-green-100 text-green-800' :
                                    order.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                                    order.status === 'collected' ? 'bg-purple-100 text-purple-800' :
                                    order.status === 'cancelled' ? 'bg-red-100 text-red-800' :
                                    'bg-yellow-100 text-yellow-800'
                                  }>
                                    {order.status}
                                  </Badge>
                                </div>
                                <div className="flex items-center justify-between mt-1">
                                  <span className="text-xs text-gray-500">{order.doctor_name || 'N/A'}</span>
                                  <span className="text-xs text-gray-600">₹{parseFloat(order.amount || 0).toFixed(2)}</span>
                                </div>
                                {order.priority !== 'normal' && (
                                  <Badge className="mt-1 bg-red-100 text-red-800 text-xs">{order.priority.toUpperCase()}</Badge>
                                )}
                                <p className="text-xs text-gray-400 mt-1">{order.order_date ? new Date(order.order_date).toLocaleString() : ''}</p>
                                {order.has_report && <p className="text-xs text-green-600 mt-1">Report available</p>}
                                {order.notes && <p className="text-xs text-gray-600 mt-1">{order.notes}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Medications sub-tab */}
                      <TabsContent value="medications" className="space-y-3 mt-3">
                        {admissionMedications.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No prescriptions linked to this admission.</p>
                        ) : (
                          <div className="space-y-3">
                            {admissionMedications.map(rx => (
                              <div key={`${rx.type}-${rx.id}`} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between mb-2">
                                  <div>
                                    <span className="font-medium">{rx.prescription_number}</span>
                                    <span className="text-gray-500 ml-2">by {rx.doctor_name}</span>
                                  </div>
                                  <Badge className={rx.status === 'dispensed' ? 'bg-green-100 text-green-800' : rx.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'}>
                                    {rx.status}
                                  </Badge>
                                </div>
                                <p className="text-xs text-gray-400 mb-2">{rx.date ? new Date(rx.date).toLocaleString() : ''}</p>
                                {rx.medicines && rx.medicines.length > 0 && (
                                  <div className="bg-gray-50 rounded p-2 space-y-1">
                                    {rx.medicines.map((med, idx) => (
                                      <div key={idx} className="flex justify-between text-xs">
                                        <span>{med.name} {med.dosage ? `- ${med.dosage}` : ''} {med.duration ? `(${med.duration})` : ''}</span>
                                        {rx.type === 'pharmacy' && <span className="text-gray-600">₹{parseFloat(med.total_price || 0).toFixed(2)}</span>}
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {rx.type === 'pharmacy' && rx.total_amount > 0 && (
                                  <div className="flex justify-between mt-2 pt-1 border-t font-medium text-xs">
                                    <span>Total</span><span>₹{parseFloat(rx.total_amount).toFixed(2)}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Bill sub-tab */}
                      <TabsContent value="bill" className="space-y-3 mt-3">
                        {billData ? (
                          <>
                            <div className="border rounded-lg p-3 text-sm space-y-2">
                              <div className="flex justify-between"><span className="text-gray-500">Room ({billData.room?.room_number} - {billData.stay_days} days)</span><span>₹{billData.room_total?.toFixed(2)}</span></div>
                              {billData.visits && Object.entries(billData.visits).map(([type, data]) => (
                                <div key={type} className="flex justify-between">
                                  <span className="text-gray-500">{type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())} (x{data.count})</span>
                                  <span>₹{data.total.toFixed(2)}</span>
                                </div>
                              ))}
                              {billData.pharmacy_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Pharmacy / Medications</span>
                                  <span>₹{billData.pharmacy_total.toFixed(2)}</span>
                                </div>
                              )}
                              {billData.lab_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Lab Tests</span>
                                  <span>₹{billData.lab_total.toFixed(2)}</span>
                                </div>
                              )}
                              <div className="border-t pt-2 flex justify-between font-semibold">
                                <span>Grand Total</span><span>₹{billData.grand_total?.toFixed(2)}</span>
                              </div>
                            </div>
                            <div className="flex gap-2">
                              <Button size="sm" onClick={handleFinalizeBill} disabled={loading}>
                                {loading ? 'Finalizing...' : 'Finalize Bill'}
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => handlePrintBillPdf(activityAdmission.id)}>
                                <FileText className="h-4 w-4 mr-1" /> Print Bill
                              </Button>
                            </div>
                          </>
                        ) : (
                          <p className="text-sm text-gray-500 text-center py-4">Loading bill...</p>
                        )}
                      </TabsContent>

                      {/* Insurance sub-tab */}
                      <TabsContent value="insurance" className="space-y-4 mt-3">
                        {(() => {
                          const adm = activityAdmission;
                          const cs = adm?.claim_status || 'none';
                          const nextActions = {
                            none: adm?.insurance_provider ? [{ status: 'draft', label: 'Create Draft Claim', variant: 'default' }] : [],
                            draft: [
                              { status: 'submitted', label: 'Submit Claim', variant: 'default' },
                              { status: 'none', label: 'Cancel Draft', variant: 'outline' },
                            ],
                            submitted: [
                              { status: 'approved', label: 'Mark Approved', variant: 'default' },
                              { status: 'rejected', label: 'Mark Rejected', variant: 'destructive' },
                              { status: 'draft', label: 'Revert to Draft', variant: 'outline' },
                            ],
                            approved: [],
                            rejected: [{ status: 'draft', label: 'Resubmit as Draft', variant: 'outline' }],
                          };

                          return (
                            <>
                              {/* Current Status */}
                              <div className="border rounded-lg p-4">
                                <div className="flex items-center justify-between mb-3">
                                  <div className="flex items-center gap-2">
                                    <Shield className="h-5 w-5 text-gray-500" />
                                    <h4 className="font-medium text-sm">Insurance Claim</h4>
                                  </div>
                                  <Badge className={claimStatusColor[cs]}>{claimStatusLabel[cs]}</Badge>
                                </div>

                                <div className="space-y-2 text-sm">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Provider</span>
                                    <span>{adm?.insurance_provider || '—'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Policy #</span>
                                    <span>{adm?.policy_number || '—'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Claim Ref</span>
                                    <span>{adm?.claim_reference || '—'}</span>
                                  </div>
                                  {adm?.claim_amount != null && adm.claim_amount > 0 && (
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Claim Amount</span>
                                      <span className="font-medium">₹{parseFloat(adm.claim_amount).toFixed(2)}</span>
                                    </div>
                                  )}
                                  {adm?.claim_submitted_at && (
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Submitted On</span>
                                      <span>{new Date(adm.claim_submitted_at).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {adm?.claim_notes && (
                                    <div className="pt-2 border-t">
                                      <span className="text-gray-500 text-xs">Notes</span>
                                      <p className="text-xs mt-1">{adm.claim_notes}</p>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Workflow Progress */}
                              <div className="flex items-center gap-1 text-xs px-1">
                                {['draft', 'submitted', 'approved'].map((step, idx) => (
                                  <React.Fragment key={step}>
                                    <div className={`flex items-center gap-1 px-2 py-1 rounded ${
                                      cs === step ? 'bg-blue-100 text-blue-800 font-medium' :
                                      (cs === 'approved' || (cs === 'submitted' && idx < 2) || (cs === 'draft' && idx < 1) || (['submitted', 'approved'].includes(cs) && idx === 0) || (cs === 'approved' && idx <= 1))
                                        ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-400'
                                    }`}>
                                      {step.charAt(0).toUpperCase() + step.slice(1)}
                                    </div>
                                    {idx < 2 && <ChevronRight className="h-3 w-3 text-gray-300" />}
                                  </React.Fragment>
                                ))}
                                {cs === 'rejected' && (
                                  <>
                                    <ChevronRight className="h-3 w-3 text-gray-300" />
                                    <div className="px-2 py-1 rounded bg-red-100 text-red-800 font-medium">Rejected</div>
                                  </>
                                )}
                              </div>

                              {/* No insurance warning */}
                              {!adm?.insurance_provider && cs === 'none' && (
                                <p className="text-sm text-gray-500 text-center py-2">
                                  No insurance provider recorded. Update admission details to add insurance info before creating a claim.
                                </p>
                              )}

                              {/* Action Buttons */}
                              {(nextActions[cs] || []).length > 0 && (
                                <div className="space-y-3">
                                  {(cs === 'none' || cs === 'draft' || cs === 'rejected') && (
                                    <div className="space-y-2">
                                      <div className="grid grid-cols-2 gap-2">
                                        <div>
                                          <Label className="text-xs">Claim Amount (₹)</Label>
                                          <Input type="number" min="0" step="0.01" placeholder="0.00"
                                            defaultValue={adm?.claim_amount || ''}
                                            id={`claim-amount-${adm?.id}`} />
                                        </div>
                                        <div>
                                          <Label className="text-xs">Claim Reference</Label>
                                          <Input placeholder="Ref #" defaultValue={adm?.claim_reference || ''}
                                            id={`claim-ref-${adm?.id}`} />
                                        </div>
                                      </div>
                                      <div>
                                        <Label className="text-xs">Notes</Label>
                                        <Textarea placeholder="Claim notes..." rows={2}
                                          defaultValue={adm?.claim_notes || ''}
                                          id={`claim-notes-${adm?.id}`} />
                                      </div>
                                    </div>
                                  )}

                                  <div className="flex gap-2 flex-wrap">
                                    {(nextActions[cs] || []).map(action => (
                                      <Button key={action.status} size="sm" variant={action.variant} disabled={loading}
                                        onClick={() => {
                                          const amountEl = document.getElementById(`claim-amount-${adm?.id}`);
                                          const refEl = document.getElementById(`claim-ref-${adm?.id}`);
                                          const notesEl = document.getElementById(`claim-notes-${adm?.id}`);
                                          handleClaimStatusUpdate(adm.id, {
                                            claim_status: action.status,
                                            claim_amount: amountEl ? parseFloat(amountEl.value) || null : null,
                                            claim_reference: refEl ? refEl.value || null : null,
                                            claim_notes: notesEl ? notesEl.value || null : null,
                                          });
                                        }}>
                                        {action.label}
                                      </Button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </TabsContent>

                      {/* Documents sub-tab */}
                      <TabsContent value="docs" className="space-y-3 mt-3">
                        {/* Upload area */}
                        <div className="border-2 border-dashed rounded-lg p-4 text-center">
                          <input type="file" id="doc-upload-input" className="hidden"
                            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.doc,.docx"
                            onChange={e => {
                              const file = e.target.files?.[0];
                              if (file && activityAdmission) {
                                const docType = prompt('Document type:\nconsent_form, referral_letter, insurance_doc, lab_report, other', 'other') || 'other';
                                handleDocUpload(activityAdmission.id, file, docType, file.name, '');
                              }
                              e.target.value = '';
                            }} />
                          <Button variant="outline" size="sm" disabled={docUploading}
                            onClick={() => document.getElementById('doc-upload-input')?.click()}>
                            <Upload className="h-4 w-4 mr-1" /> {docUploading ? 'Uploading...' : 'Upload Document'}
                          </Button>
                          <p className="text-xs text-gray-400 mt-1">PDF, images, Word docs (max 10MB)</p>
                        </div>

                        {admissionDocs.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No documents attached.</p>
                        ) : (
                          <div className="space-y-2">
                            {admissionDocs.map(doc => (
                              <div key={doc.id} className="border rounded-lg p-3 text-sm flex items-center justify-between">
                                <div className="flex items-center gap-2 min-w-0">
                                  <Paperclip className="h-4 w-4 text-gray-400 shrink-0" />
                                  <div className="min-w-0">
                                    <p className="font-medium truncate">{doc.document_name}</p>
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                      <Badge className="bg-gray-100 text-gray-700 text-xs">{doc.document_type.replace('_', ' ')}</Badge>
                                      <span>{doc.file_size ? `${(doc.file_size / 1024).toFixed(0)} KB` : ''}</span>
                                      <span>{doc.uploaded_by_name || ''}</span>
                                      <span>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ''}</span>
                                    </div>
                                    {doc.notes && <p className="text-xs text-gray-400 mt-1">{doc.notes}</p>}
                                  </div>
                                </div>
                                <div className="flex gap-1 shrink-0">
                                  <Button variant="ghost" size="sm" onClick={() => {
                                    window.open(`/api/inpatient/documents/${doc.id}/download`, '_blank');
                                  }} title="Download">
                                    <Download className="h-4 w-4" />
                                  </Button>
                                  <Button variant="ghost" size="sm" className="text-red-500"
                                    onClick={() => setConfirmState({
                                      open: true, title: 'Delete Document',
                                      message: `Delete "${doc.document_name}"?`,
                                      onConfirm: () => { setConfirmState({ open: false }); handleDocDelete(doc.id); }
                                    })} title="Delete">
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>
                    </Tabs>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ============ ROOM MANAGEMENT ============ */}
          {activeTab === 'rooms' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Room Management</h2>
            <Button onClick={() => { setEditingRoom(null); resetRoomForm(); setShowRoomDialog(true); }}>
              <Plus className="h-4 w-4 mr-2" /> Add Room
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {rooms.map(room => (
              <Card key={room.id} className={!room.is_active ? 'opacity-50' : ''}>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="font-semibold">{room.room_number}</h3>
                      <Badge className="mt-1">{roomTypeLabel[room.room_type] || room.room_type}</Badge>
                    </div>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openBedManager(room)} title="Manage Beds"><Bed className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => handleEditRoom(room)}><Edit2 className="h-4 w-4" /></Button>
                      {room.is_active && (
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => {
                          setConfirmState({ open: true, title: 'Deactivate Room', message: `Deactivate room ${room.room_number}?`,
                            onConfirm: () => { setConfirmState({ open: false }); handleDeleteRoom(room.id); } });
                        }}><Trash2 className="h-4 w-4" /></Button>
                      )}
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    {room.floor && <p>Floor: {room.floor}</p>}
                    {room.department && <p>Dept: {room.department}</p>}
                    <p>Beds: {room.available_beds}/{room.bed_count} available</p>
                    <p>Charge: ₹{room.room_charge_per_day}/day</p>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className={`h-2 rounded-full ${room.available_beds === 0 ? 'bg-red-500' : 'bg-green-500'}`}
                         style={{ width: `${room.bed_count > 0 ? ((room.bed_count - room.available_beds) / room.bed_count * 100) : 0}%` }} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Rate Config */}
          <Card className="mt-6">
            <CardHeader><CardTitle className="text-lg">Rate Configuration</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label>Doctor Visit Rate (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={rateForm.doctor_visit_rate}
                         onChange={e => setRateForm(p => ({ ...p, doctor_visit_rate: e.target.value }))} />
                </div>
                <div>
                  <Label>Nurse Visit Rate (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={rateForm.nurse_visit_rate}
                         onChange={e => setRateForm(p => ({ ...p, nurse_visit_rate: e.target.value }))} />
                </div>
                <div>
                  <Label>Procedure Rate (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={rateForm.procedure_rate}
                         onChange={e => setRateForm(p => ({ ...p, procedure_rate: e.target.value }))} />
                </div>
              </div>
              <Button className="mt-4" onClick={handleSaveRateConfig} disabled={loading}>
                {loading ? 'Saving...' : 'Save Rates'}
              </Button>
            </CardContent>
          </Card>
          </div>
          )}

          {/* ============ DISCHARGE HISTORY ============ */}
          {activeTab === 'discharge' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input placeholder="Search discharged patients..." value={dischargeSearch} onChange={e => setDischargeSearch(e.target.value)} className="pl-10" />
          </div>

          {filteredDischarged.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-gray-500">No discharged patients found.</CardContent></Card>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 text-sm">Patient</th>
                    <th className="text-left py-2 text-sm">Admission #</th>
                    <th className="text-left py-2 text-sm">Admitted</th>
                    <th className="text-left py-2 text-sm">Doctor</th>
                    <th className="text-left py-2 text-sm">Status</th>
                    <th className="text-left py-2 text-sm">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDischarged.map(adm => (
                    <tr key={adm.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 text-sm font-medium">{adm.patient_name || 'N/A'}</td>
                      <td className="py-2 text-sm">{adm.admission_number}</td>
                      <td className="py-2 text-sm">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : ''}</td>
                      <td className="py-2 text-sm">{adm.doctor_name || 'N/A'}</td>
                      <td className="py-2"><Badge className={admissionStatusColor[adm.status] || ''}>{adm.status}</Badge></td>
                      <td className="py-2">
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={() => handlePrintDischargePdf(adm.id)} title="Discharge Summary PDF">
                            <FileText className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handlePrintBillPdf(adm.id)} title="Bill PDF">
                            <DollarSign className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {dischargeTotal > PAGE_SIZE && (
                <div className="flex items-center justify-between pt-4 border-t mt-2">
                  <span className="text-sm text-gray-500">
                    Showing {dischargePage * PAGE_SIZE + 1}–{Math.min((dischargePage + 1) * PAGE_SIZE, dischargeTotal)} of {dischargeTotal}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={dischargePage === 0}
                      onClick={() => setDischargePage(p => p - 1)}>
                      <ChevronLeft className="h-4 w-4 mr-1" /> Prev
                    </Button>
                    <Button variant="outline" size="sm" disabled={(dischargePage + 1) * PAGE_SIZE >= dischargeTotal}
                      onClick={() => setDischargePage(p => p + 1)}>
                      Next <ChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          </div>
          )}

          {/* ============ OT SCHEDULE ============ */}
          {activeTab === 'ot' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">OT Schedule</h2>
            <Button onClick={() => setShowOTDialog(true)}>
              <Plus className="h-4 w-4 mr-2" /> Schedule OT
            </Button>
          </div>

          {otSchedules.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-gray-500">No OT schedules found.</CardContent></Card>
          ) : (
            <div className="space-y-3">
              {otSchedules.map(ot => (
                <Card key={ot.id}>
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold text-sm">{ot.procedure_name}</h3>
                          <Badge className={otStatusColor[ot.status] || ''}>{ot.status.replace('_', ' ')}</Badge>
                        </div>
                        <p className="text-sm text-gray-600">
                          <User className="h-3 w-3 inline mr-1" /> {ot.patient_name || 'N/A'} &bull;
                          <Stethoscope className="h-3 w-3 inline mx-1" /> Dr. {ot.surgeon_name || 'N/A'} &bull;
                          <Clock className="h-3 w-3 inline mx-1" /> {ot.scheduled_date ? new Date(ot.scheduled_date).toLocaleString() : ''} &bull;
                          OT Room: {ot.ot_room_number}
                          {ot.estimated_duration_minutes && <span> &bull; ~{ot.estimated_duration_minutes} min</span>}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        {ot.status === 'scheduled' && (
                          <>
                            <Button size="sm" variant="outline" onClick={() => handleUpdateOTStatus(ot.id, 'in_progress')}>Start</Button>
                            <Button size="sm" variant="ghost" className="text-red-500" onClick={() => handleUpdateOTStatus(ot.id, 'cancelled')}>Cancel</Button>
                          </>
                        )}
                        {ot.status === 'in_progress' && (
                          <Button size="sm" variant="outline" onClick={() => handleUpdateOTStatus(ot.id, 'completed')}>Complete</Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          </div>
          )}

        </div>
      </div>

      {/* ============================================================ */}
      {/* DIALOGS */}
      {/* ============================================================ */}

      {/* Admission Dialog */}
      <Dialog open={showAdmissionDialog} onOpenChange={setShowAdmissionDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Admission</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateAdmission} className="space-y-4">
            {/* Patient search */}
            <div>
              <Label>Patient *</Label>
              <div className="relative">
                <Input placeholder="Search patient by name or phone..." value={patientSearchQuery}
                  onChange={e => { setPatientSearchQuery(e.target.value); setAdmissionForm(p => ({ ...p, patient_id: '' })); setSelectedPatientName(''); }} />
                {selectedPatientName && <p className="text-sm text-green-600 mt-1">Selected: {selectedPatientName}</p>}
                {patientSearchResults.length > 0 && !admissionForm.patient_id && (
                  <div className="absolute z-10 w-full bg-white border rounded-lg shadow-lg mt-1 max-h-40 overflow-y-auto">
                    {patientSearchResults.map(p => (
                      <div key={p.id} className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                        onClick={() => { setAdmissionForm(prev => ({ ...prev, patient_id: p.id })); setSelectedPatientName(`${p.first_name} ${p.last_name}`); setPatientSearchQuery(''); setPatientSearchResults([]); }}>
                        {p.first_name} {p.last_name} <span className="text-gray-400">{p.phone}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Admitting Doctor *</Label>
                <Select value={admissionForm.admitting_doctor_id ? String(admissionForm.admitting_doctor_id) : ''} onValueChange={v => setAdmissionForm(p => ({ ...p, admitting_doctor_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (
                      <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Room *</Label>
                <Select value={admissionForm.room_id ? String(admissionForm.room_id) : ''} onValueChange={v => {
                  setAdmissionForm(p => ({ ...p, room_id: v, bed_id: '' }));
                  // Fetch beds for selected room
                  axios.get(`/api/inpatient/rooms/${v}/beds`).then(res => setAdmissionBeds(res.data)).catch(() => setAdmissionBeds([]));
                }}>
                  <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
                  <SelectContent>
                    {availableRooms.map(r => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.room_number} ({roomTypeLabel[r.room_type]}) - {r.available_beds} beds avail - ₹{r.room_charge_per_day}/day
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {admissionBeds.length > 0 && (
                <div>
                  <Label>Bed</Label>
                  <Select value={admissionForm.bed_id ? String(admissionForm.bed_id) : ''} onValueChange={v => setAdmissionForm(p => ({ ...p, bed_id: v }))}>
                    <SelectTrigger><SelectValue placeholder="Select bed" /></SelectTrigger>
                    <SelectContent>
                      {admissionBeds.filter(b => b.status === 'available').map(b => (
                        <SelectItem key={b.id} value={String(b.id)}>
                          Bed {b.bed_label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Admission Type *</Label>
                <Select value={admissionForm.admission_type} onValueChange={v => setAdmissionForm(p => ({ ...p, admission_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="elective">Elective</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Condition</Label>
                <Select value={admissionForm.condition_on_admission} onValueChange={v => setAdmissionForm(p => ({ ...p, condition_on_admission: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="serious">Serious</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Estimated Stay (days)</Label>
                <Input type="number" min="1" value={admissionForm.estimated_stay_days} onChange={e => setAdmissionForm(p => ({ ...p, estimated_stay_days: e.target.value }))} />
              </div>
              <div>
                <Label>Bed Number</Label>
                <Input value={admissionForm.bed_number} onChange={e => setAdmissionForm(p => ({ ...p, bed_number: e.target.value }))} />
              </div>
            </div>

            <div>
              <Label>Admission Reason</Label>
              <Textarea value={admissionForm.admission_reason} onChange={e => setAdmissionForm(p => ({ ...p, admission_reason: e.target.value }))} rows={2} />
            </div>

            <div>
              <Label>Emergency Contact</Label>
              <Input value={admissionForm.emergency_contact} onChange={e => setAdmissionForm(p => ({ ...p, emergency_contact: e.target.value }))} />
            </div>

            <div className="border-t pt-4">
              <h4 className="font-medium text-sm mb-3">Insurance (Optional)</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Insurance Provider</Label>
                  <Input placeholder="Provider name" value={admissionForm.insurance_provider}
                    onChange={e => setAdmissionForm(p => ({ ...p, insurance_provider: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Policy Number</Label>
                  <Input placeholder="Policy #" value={admissionForm.policy_number}
                    onChange={e => setAdmissionForm(p => ({ ...p, policy_number: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Claim Reference</Label>
                  <Input placeholder="Claim ref" value={admissionForm.claim_reference}
                    onChange={e => setAdmissionForm(p => ({ ...p, claim_reference: e.target.value }))} />
                </div>
              </div>
            </div>

            <div>
              <Label>Additional Notes</Label>
              <Textarea value={admissionForm.admission_notes} onChange={e => setAdmissionForm(p => ({ ...p, admission_notes: e.target.value }))} rows={2} />
            </div>

            <Button type="submit" className="w-full" disabled={loading || !admissionForm.patient_id || !admissionForm.admitting_doctor_id || !admissionForm.room_id}>
              {loading ? 'Admitting...' : 'Admit Patient'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Visit Dialog */}
      <Dialog open={showVisitDialog} onOpenChange={setShowVisitDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Visit</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateVisit} className="space-y-4">
            <div>
              <Label>Visit Type *</Label>
              <Select value={visitForm.visit_type} onValueChange={v => setVisitForm(p => ({ ...p, visit_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="doctor_visit">Doctor Visit</SelectItem>
                  <SelectItem value="nurse_visit">Nurse Visit</SelectItem>
                  <SelectItem value="procedure">Procedure</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Visitor (Staff) *</Label>
              <Select value={visitForm.visitor_id ? String(visitForm.visitor_id) : ''} onValueChange={v => setVisitForm(p => ({ ...p, visitor_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>{d.first_name} {d.last_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {rateConfig && (
              <p className="text-xs text-gray-500">
                Auto-charge: ₹{visitForm.visit_type === 'doctor_visit' ? rateConfig.doctor_visit_rate :
                  visitForm.visit_type === 'nurse_visit' ? rateConfig.nurse_visit_rate : rateConfig.procedure_rate}
              </p>
            )}
            <div>
              <Label>Notes</Label>
              <Textarea value={visitForm.notes} onChange={e => setVisitForm(p => ({ ...p, notes: e.target.value }))} rows={3} />
            </div>
            <Button type="submit" className="w-full" disabled={loading || !visitForm.visitor_id}>
              {loading ? 'Saving...' : 'Record Visit'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Nursing Note Dialog */}
      <Dialog open={showNursingNoteDialog} onOpenChange={(open) => { setShowNursingNoteDialog(open); if (!open) setEditingNursingNote(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingNursingNote ? 'Edit Nursing Note' : 'Add Nursing Note'}</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateNursingNote} className="space-y-4">
            <div>
              <Label>Shift *</Label>
              <Select value={nursingNoteForm.shift} onValueChange={v => setNursingNoteForm(p => ({ ...p, shift: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="morning">Morning</SelectItem>
                  <SelectItem value="afternoon">Afternoon</SelectItem>
                  <SelectItem value="night">Night</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Note Type *</Label>
              <Select value={nursingNoteForm.note_type} onValueChange={v => setNursingNoteForm(p => ({ ...p, note_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="observation">Observation</SelectItem>
                  <SelectItem value="medication">Medication</SelectItem>
                  <SelectItem value="vitals">Vitals</SelectItem>
                  <SelectItem value="procedure">Procedure</SelectItem>
                  <SelectItem value="handover">Handover</SelectItem>
                  <SelectItem value="general">General</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Content *</Label>
              <Textarea value={nursingNoteForm.content} onChange={e => setNursingNoteForm(p => ({ ...p, content: e.target.value }))} rows={5} placeholder="Enter nursing note details..." />
            </div>
            <Button type="submit" className="w-full" disabled={loading || !nursingNoteForm.content.trim()}>
              {loading ? 'Saving...' : editingNursingNote ? 'Update Note' : 'Add Note'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Lab Order Dialog */}
      <Dialog open={showLabOrderDialog} onOpenChange={setShowLabOrderDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Order Lab Tests</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateLabOrder} className="space-y-4">
            <div>
              <Label>Priority</Label>
              <Select value={labOrderForm.priority} onValueChange={v => setLabOrderForm(p => ({ ...p, priority: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="stat">STAT</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Search Tests</Label>
              <Input placeholder="Search by test name or code..." value={labTestSearch}
                onChange={e => setLabTestSearch(e.target.value)} />
            </div>
            <div className="border rounded-lg max-h-48 overflow-y-auto">
              {availableLabTests
                .filter(t => !labTestSearch || t.name.toLowerCase().includes(labTestSearch.toLowerCase()) || (t.test_code && t.test_code.toLowerCase().includes(labTestSearch.toLowerCase())))
                .map(t => (
                  <label key={t.id} className={`flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 border-b last:border-b-0 ${labOrderForm.test_ids.includes(t.id) ? 'bg-blue-50' : ''}`}>
                    <div className="flex items-center gap-2">
                      <input type="checkbox" checked={labOrderForm.test_ids.includes(t.id)} onChange={() => toggleLabTest(t.id)} className="rounded" />
                      <div>
                        <span className="text-sm font-medium">{t.name}</span>
                        {t.test_code && <span className="text-xs text-gray-400 ml-1">({t.test_code})</span>}
                      </div>
                    </div>
                    <span className="text-sm text-gray-600">₹{parseFloat(t.cost || 0).toFixed(2)}</span>
                  </label>
                ))}
              {availableLabTests.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">No lab tests available</p>
              )}
            </div>
            {labOrderForm.test_ids.length > 0 && (
              <p className="text-sm font-medium">
                Selected: {labOrderForm.test_ids.length} test(s) — Total: ₹{availableLabTests
                  .filter(t => labOrderForm.test_ids.includes(t.id))
                  .reduce((sum, t) => sum + (t.cost || 0), 0).toFixed(2)}
              </p>
            )}
            <div>
              <Label>Notes</Label>
              <Textarea value={labOrderForm.notes} onChange={e => setLabOrderForm(p => ({ ...p, notes: e.target.value }))} rows={2} placeholder="Optional clinical notes..." />
            </div>
            <Button type="submit" className="w-full" disabled={loading || labOrderForm.test_ids.length === 0}>
              {loading ? 'Ordering...' : `Order ${labOrderForm.test_ids.length} Test(s)`}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Discharge Dialog */}
      <Dialog open={showDischargeDialog} onOpenChange={setShowDischargeDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Discharge Patient - {dischargeAdmission?.patient_name}</DialogTitle></DialogHeader>
          <form onSubmit={handleDischarge} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Discharge Type *</Label>
                <Select value={dischargeForm.discharge_type} onValueChange={v => setDischargeForm(p => ({ ...p, discharge_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="against_advice">Against Advice</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                    <SelectItem value="death">Death</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Condition on Discharge</Label>
                <Select value={dischargeForm.condition_on_discharge} onValueChange={v => setDischargeForm(p => ({ ...p, condition_on_discharge: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="improved">Improved</SelectItem>
                    <SelectItem value="unchanged">Unchanged</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Diagnosis on Discharge</Label>
              <Textarea value={dischargeForm.diagnosis_on_discharge} onChange={e => setDischargeForm(p => ({ ...p, diagnosis_on_discharge: e.target.value }))} rows={2} />
            </div>
            <div>
              <Label>Treatment Given</Label>
              <Textarea value={dischargeForm.treatment_given} onChange={e => setDischargeForm(p => ({ ...p, treatment_given: e.target.value }))} rows={2} />
            </div>
            <div>
              <Label>Discharge Summary</Label>
              <Textarea value={dischargeForm.discharge_summary} onChange={e => setDischargeForm(p => ({ ...p, discharge_summary: e.target.value }))} rows={2} />
            </div>
            <div>
              <Label>Medications Prescribed</Label>
              <Textarea value={dischargeForm.medications_prescribed} onChange={e => setDischargeForm(p => ({ ...p, medications_prescribed: e.target.value }))} rows={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Follow-up Instructions</Label>
                <Textarea value={dischargeForm.follow_up_instructions} onChange={e => setDischargeForm(p => ({ ...p, follow_up_instructions: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Follow-up Date</Label>
                <Input type="date" value={dischargeForm.follow_up_date} onChange={e => setDischargeForm(p => ({ ...p, follow_up_date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Diet Instructions</Label>
                <Textarea value={dischargeForm.diet_instructions} onChange={e => setDischargeForm(p => ({ ...p, diet_instructions: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Activity Restrictions</Label>
                <Textarea value={dischargeForm.activity_restrictions} onChange={e => setDischargeForm(p => ({ ...p, activity_restrictions: e.target.value }))} rows={2} />
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Discharging...' : 'Confirm Discharge'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Room Dialog */}
      <Dialog open={showRoomDialog} onOpenChange={setShowRoomDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingRoom ? 'Edit Room' : 'Add Room'}</DialogTitle></DialogHeader>
          <form onSubmit={handleSaveRoom} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Room Number *</Label>
                <Input required value={roomForm.room_number} onChange={e => setRoomForm(p => ({ ...p, room_number: e.target.value }))} />
              </div>
              <div>
                <Label>Room Type *</Label>
                <Select value={roomForm.room_type} onValueChange={v => setRoomForm(p => ({ ...p, room_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="private">Private</SelectItem>
                    <SelectItem value="icu">ICU</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                    <SelectItem value="operation">Operation</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Floor</Label><Input value={roomForm.floor} onChange={e => setRoomForm(p => ({ ...p, floor: e.target.value }))} /></div>
              <div><Label>Department</Label><Input value={roomForm.department} onChange={e => setRoomForm(p => ({ ...p, department: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Bed Count *</Label><Input type="number" min="1" required value={roomForm.bed_count} onChange={e => setRoomForm(p => ({ ...p, bed_count: e.target.value }))} /></div>
              <div><Label>Charge / Day (₹) *</Label><Input type="number" min="0" step="0.01" required value={roomForm.room_charge_per_day} onChange={e => setRoomForm(p => ({ ...p, room_charge_per_day: e.target.value }))} /></div>
            </div>
            <div><Label>Amenities</Label><Input value={roomForm.amenities} onChange={e => setRoomForm(p => ({ ...p, amenities: e.target.value }))} placeholder="AC, TV, Attached Bath..." /></div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving...' : editingRoom ? 'Update Room' : 'Create Room'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* OT Schedule Dialog */}
      <Dialog open={showOTDialog} onOpenChange={setShowOTDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Schedule OT</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateOT} className="space-y-4">
            <div>
              <Label>Patient *</Label>
              <div className="relative">
                <Input placeholder="Search patient..." value={patientSearchQuery}
                  onChange={e => { setPatientSearchQuery(e.target.value); setOtForm(p => ({ ...p, patient_id: '' })); setSelectedPatientName(''); }} />
                {selectedPatientName && otForm.patient_id && <p className="text-sm text-green-600 mt-1">Selected: {selectedPatientName}</p>}
                {patientSearchResults.length > 0 && !otForm.patient_id && (
                  <div className="absolute z-10 w-full bg-white border rounded-lg shadow-lg mt-1 max-h-40 overflow-y-auto">
                    {patientSearchResults.map(p => (
                      <div key={p.id} className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                        onClick={() => { setOtForm(prev => ({ ...prev, patient_id: p.id })); setSelectedPatientName(`${p.first_name} ${p.last_name}`); setPatientSearchQuery(''); setPatientSearchResults([]); }}>
                        {p.first_name} {p.last_name} <span className="text-gray-400">{p.phone}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div>
              <Label>Surgeon *</Label>
              <Select value={otForm.surgeon_id ? String(otForm.surgeon_id) : ''} onValueChange={v => setOtForm(p => ({ ...p, surgeon_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select surgeon" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (<SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div><Label>Procedure Name *</Label><Input required value={otForm.procedure_name} onChange={e => setOtForm(p => ({ ...p, procedure_name: e.target.value }))} /></div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>OT Room *</Label><Input required value={otForm.ot_room_number} onChange={e => setOtForm(p => ({ ...p, ot_room_number: e.target.value }))} /></div>
              <div><Label>Duration (min)</Label><Input type="number" min="1" value={otForm.estimated_duration_minutes} onChange={e => setOtForm(p => ({ ...p, estimated_duration_minutes: e.target.value }))} /></div>
            </div>
            <div><Label>Scheduled Date & Time *</Label><Input type="datetime-local" required value={otForm.scheduled_date} onChange={e => setOtForm(p => ({ ...p, scheduled_date: e.target.value }))} /></div>
            <div><Label>Pre-Op Notes</Label><Textarea value={otForm.pre_op_notes} onChange={e => setOtForm(p => ({ ...p, pre_op_notes: e.target.value }))} rows={2} /></div>
            <Button type="submit" className="w-full" disabled={loading || !otForm.patient_id || !otForm.surgeon_id}>
              {loading ? 'Scheduling...' : 'Schedule OT'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Bed Manager Dialog */}
      <Dialog open={showBedManager} onOpenChange={setShowBedManager}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Manage Beds — {selectedRoomForBeds?.room_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2">
              <Input placeholder="Bed label (e.g. A, B, 1, 2)" value={newBedLabel}
                onChange={e => setNewBedLabel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleAddBed(); }} />
              <Button size="sm" onClick={handleAddBed} disabled={!newBedLabel.trim()}>
                <Plus className="h-4 w-4 mr-1" /> Add
              </Button>
            </div>
            {roomBeds.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No beds configured. Add beds above.</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {roomBeds.map(bed => (
                  <div key={bed.id} className="flex items-center justify-between border rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Bed className="h-4 w-4 text-gray-400" />
                      <span className="font-medium text-sm">{bed.bed_label}</span>
                      <Badge className={
                        bed.status === 'available' ? 'bg-green-100 text-green-800' :
                        bed.status === 'occupied' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }>{bed.status}</Badge>
                    </div>
                    <div className="flex gap-1">
                      {bed.status === 'available' && (
                        <Button variant="ghost" size="sm" className="text-yellow-600 h-7 text-xs"
                          onClick={() => handleUpdateBedStatus(bed.id, 'maintenance')} title="Set Maintenance">
                          <Clock className="h-3 w-3" />
                        </Button>
                      )}
                      {bed.status === 'maintenance' && (
                        <Button variant="ghost" size="sm" className="text-green-600 h-7 text-xs"
                          onClick={() => handleUpdateBedStatus(bed.id, 'available')} title="Set Available">
                          <Activity className="h-3 w-3" />
                        </Button>
                      )}
                      {!bed.current_admission_id && (
                        <Button variant="ghost" size="sm" className="text-red-500 h-7"
                          onClick={() => handleDeleteBed(bed.id)} title="Delete">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-400">
              {roomBeds.length} bed{roomBeds.length !== 1 ? 's' : ''} total, {roomBeds.filter(b => b.status === 'available').length} available
            </p>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm Dialog */}
      <ConfirmDialog open={confirmState.open} title={confirmState.title} message={confirmState.message}
        onConfirm={confirmState.onConfirm} onCancel={() => setConfirmState({ open: false })} />
    </div>
  );
};

export default InpatientModule;
