import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import {
  ArrowLeft, Stethoscope, Activity, Pill, TestTube, FileText, CheckCircle,
  Clock, User, AlertCircle, Eye, Plus, Trash2, Save, Printer, Search,
  ChevronRight, ChevronDown, History
} from 'lucide-react';
import { format } from 'date-fns';
import axios from 'axios';

const ConsultationPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const appointmentId = searchParams.get('appointmentId');
  const patientId = searchParams.get('patientId');
  const patientUuidParam = searchParams.get('patientUuid') || '';
  const patientName = searchParams.get('patientName') || '';

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('vitals');
  const [feedback, setFeedback] = useState({ message: '', type: '' });

  // Consultation
  const [activeConsultation, setActiveConsultation] = useState(null);
  const [consultationForm, setConsultationForm] = useState({
    chief_complaint: '', present_history: '', examination_findings: '',
    notes: '', follow_up_date: ''
  });

  // Vitals
  const [vitalsForm, setVitalsForm] = useState({
    blood_pressure_systolic: '', blood_pressure_diastolic: '',
    heart_rate: '', temperature: '', weight: '', height: '',
    respiratory_rate: '', oxygen_saturation: '', bmi: '', notes: ''
  });

  // Prescription
  const [prescriptionForm, setPrescriptionForm] = useState({
    medications: [{ medicine_name: '', quantity_prescribed: 1, dosage: '', frequency_schedule: '1-0-0', food_timing: 'after_food', duration: '', instructions: '' }],
    diagnosis: '', notes: '', follow_up_date: ''
  });
  const [prescriptions, setPrescriptions] = useState([]);
  const [currentPrescriptionId, setCurrentPrescriptionId] = useState(null);
  const [consultationHistory, setConsultationHistory] = useState([]);
  const [expandedHistoryItems, setExpandedHistoryItems] = useState({});
  const [savedPrescription, setSavedPrescription] = useState(null);
  const [rxPdfUrl, setRxPdfUrl] = useState(null);
  const [rxIncludeHeader, setRxIncludeHeader] = useState(true);

  // Lab Order
  const [availableLabTests, setAvailableLabTests] = useState([]);
  const [labCategories, setLabCategories] = useState([]);
  const [selectedLabTests, setSelectedLabTests] = useState([]);
  const [labOrderPriority, setLabOrderPriority] = useState('normal');
  const [labOrderNotes, setLabOrderNotes] = useState('');
  const [labSearchQuery, setLabSearchQuery] = useState('');
  const [labCategoryFilter, setLabCategoryFilter] = useState('all');
  const [customLabTests, setCustomLabTests] = useState([]);
  const [customLabTestInput, setCustomLabTestInput] = useState('');

  // Lab Results
  const [labOrders, setLabOrders] = useState([]);
  const [expandedReport, setExpandedReport] = useState(null);
  const [expandedLabGroups, setExpandedLabGroups] = useState({});
  const [expandedRxGroups, setExpandedRxGroups] = useState({});

  // Appointment info
  const [appointment, setAppointment] = useState(null);

  // Use URL param first, fallback to fetched appointment data
  const patientUuid = patientUuidParam || appointment?.patient_uuid || '';

  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback({ message: '', type: '' }), 3000);
  };

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // ============ Fetch data on mount ============

  useEffect(() => {
    if (appointmentId) {
      fetchAppointment();
    }
    if (patientId) {
      fetchPatientLabOrders();
      fetchPatientPrescriptions();
    }
    fetchLabTests();
  }, [appointmentId, patientId]);

  // Fetch existing vitals when patientUuid is available
  useEffect(() => {
    if (patientUuid) {
      fetchExistingVitals();
    }
  }, [patientUuid]);

  // Load existing prescription for this consultation
  useEffect(() => {
    if (activeConsultation?.id) {
      fetchConsultationPrescription(activeConsultation.id);
    }
  }, [activeConsultation?.id]);

  // BMI auto-calc
  useEffect(() => {
    if (vitalsForm.weight && vitalsForm.height) {
      const w = parseFloat(vitalsForm.weight);
      const h = parseFloat(vitalsForm.height) / 100;
      if (w > 0 && h > 0) {
        setVitalsForm(prev => ({ ...prev, bmi: (w / (h * h)).toFixed(1) }));
      }
    }
  }, [vitalsForm.weight, vitalsForm.height]);

  const fetchAppointment = async () => {
    try {
      const res = await fetch(`/api/appointments/${appointmentId}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setAppointment(data);
        setConsultationForm(prev => ({ ...prev, chief_complaint: data.reason || '' }));
      }
      // Try to load existing consultation for this appointment
      const consultRes = await fetch(`/api/consultations/by-appointment/${appointmentId}`, { headers });
      if (consultRes.ok) {
        const consultData = await consultRes.json();
        setActiveConsultation(consultData);
        setConsultationForm({
          chief_complaint: consultData.chief_complaint || '',
          present_history: consultData.present_history || '',
          examination_findings: consultData.examination_findings || '',
          notes: consultData.notes || '',
          follow_up_date: consultData.follow_up_date ? consultData.follow_up_date.split('T')[0] : ''
        });
      }
    } catch (err) {
      console.error('Failed to fetch appointment:', err);
    }
  };

  const fetchPatientLabOrders = async () => {
    try {
      const res = await fetch(`/api/lab/orders?patient_id=${patientId}`, { headers });
      if (res.ok) setLabOrders(await res.json());
    } catch (err) {
      console.error('Failed to fetch lab orders:', err);
    }
  };

  const fetchPatientPrescriptions = async () => {
    try {
      const res = await fetch(`/api/prescriptions-simple/?patient_id=${patientUuid}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setPrescriptions(Array.isArray(data) ? data : data.prescriptions || []);
      }
    } catch (err) {
      console.error('Failed to fetch prescriptions:', err);
    }
  };

  const fetchLabTests = async () => {
    try {
      const [testsRes, catsRes] = await Promise.all([
        fetch('/api/lab/tests', { headers }),
        fetch('/api/lab/categories', { headers })
      ]);
      if (testsRes.ok) setAvailableLabTests(await testsRes.json());
      if (catsRes.ok) setLabCategories(await catsRes.json());
    } catch (err) {
      console.error('Failed to fetch lab tests:', err);
    }
  };

  const fetchExistingVitals = async () => {
    try {
      const res = await fetch(`/api/patients/${patientUuid}/vitals`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (data.length > 0) {
          // Pre-fill with the most recent vitals
          const latest = data[0].vital_signs;
          if (latest) {
            const bp = latest.blood_pressure?.split('/') || ['', ''];
            setVitalsForm(prev => ({
              ...prev,
              blood_pressure_systolic: bp[0] || prev.blood_pressure_systolic,
              blood_pressure_diastolic: bp[1] || prev.blood_pressure_diastolic,
              heart_rate: latest.heart_rate || prev.heart_rate,
              temperature: latest.temperature || prev.temperature,
              weight: latest.weight || prev.weight,
              height: latest.height || prev.height,
              respiratory_rate: latest.respiratory_rate || prev.respiratory_rate,
              oxygen_saturation: latest.oxygen_saturation || prev.oxygen_saturation,
              bmi: latest.bmi || prev.bmi
            }));
          }
        }
      }
    } catch (err) {
      console.error('Failed to fetch existing vitals:', err);
    }
  };

  const fetchConsultationPrescription = async (consultationId) => {
    try {
      const res = await fetch(`/api/prescriptions-simple/?consultation_id=${consultationId}`, { headers });
      if (res.ok) {
        const data = await res.json();
        const prescriptions = Array.isArray(data) ? data : data.prescriptions || [];
        if (prescriptions.length > 0) {
          const existing = prescriptions[0];
          setCurrentPrescriptionId(existing.prescription_id);
          setSavedPrescription(existing);
          // Load medicines into the form
          const meds = (existing.medicines || []).map(m => ({
            medicine_name: m.name || '',
            quantity_prescribed: m.quantity ? parseInt(m.quantity) || 1 : 1,
            dosage: m.dosage || '',
            frequency_schedule: m.frequency_schedule || '1-0-0',
            food_timing: m.food_timing || 'after_food',
            duration: m.duration || '',
            instructions: m.instructions || ''
          }));
          setPrescriptionForm(prev => ({
            ...prev,
            medications: meds.length > 0 ? meds : prev.medications,
            diagnosis: existing.diagnosis || prev.diagnosis,
            notes: existing.notes || prev.notes
          }));
        }
      }
    } catch (err) {
      console.error('Failed to fetch consultation prescription:', err);
    }
  };

  const fetchConsultationHistory = async () => {
    if (!patientId) return;
    try {
      const res = await fetch(`/api/consultations/patient/${patientId}/history`, { headers });
      if (res.ok) {
        const data = await res.json();
        // Exclude current consultation/appointment from history
        const currentConsultId = activeConsultation?.id;
        const currentAptId = appointmentId ? parseInt(appointmentId) : null;
        const filtered = data.filter(c =>
          c.id !== currentConsultId && c.appointment_id !== currentAptId
        );
        setConsultationHistory(filtered);
      }
    } catch (err) {
      console.error('Failed to fetch consultation history:', err);
    }
  };

  const fetchRxPdf = async (prescriptionId, includeHeader) => {
    try {
      const res = await fetch(`/api/prescriptions-simple/${prescriptionId}/download?include_header=${includeHeader}`, { headers });
      if (res.ok) {
        const blob = await res.blob();
        if (rxPdfUrl) window.URL.revokeObjectURL(rxPdfUrl);
        setRxPdfUrl(window.URL.createObjectURL(blob));
      }
    } catch (err) {
      console.error('Failed to fetch prescription PDF:', err);
    }
  };

  // ============ Consultation ============

  const handleSaveConsultation = async () => {
    setSaving(true);
    try {
      if (activeConsultation) {
        const res = await fetch(`/api/consultations/by-id/${activeConsultation.id}`, {
          method: 'PUT', headers,
          body: JSON.stringify({ ...consultationForm, follow_up_date: consultationForm.follow_up_date || null })
        });
        if (res.ok) {
          setActiveConsultation(await res.json());
          showFeedback('Findings updated');
        }
      } else {
        const res = await fetch('/api/consultations/', {
          method: 'POST', headers,
          body: JSON.stringify({
            patient_id: parseInt(patientId), appointment_id: parseInt(appointmentId),
            consultation_type: appointment?.appointment_type === 'followup' ? 'followup' : 'outpatient',
            chief_complaint: consultationForm.chief_complaint,
            present_history: consultationForm.present_history,
            examination_findings: consultationForm.examination_findings,
            consultation_fee: appointment?.consultation_fee || 0,
            notes: consultationForm.notes
          })
        });
        if (res.ok) {
          setActiveConsultation(await res.json());
          showFeedback('Findings saved');
        } else {
          const err = await res.json();
          showFeedback(typeof err.detail === 'string' ? err.detail : 'Failed to save findings', 'error');
        }
      }
    } catch (err) {
      showFeedback('Error saving findings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleCompleteConsultation = async () => {
    if (!activeConsultation) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/consultations/by-id/${activeConsultation.id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ ...consultationForm, status: 'completed', follow_up_date: consultationForm.follow_up_date || null })
      });
      if (res.ok) {
        showFeedback('Consultation completed');
        setTimeout(() => navigate('/dashboard'), 1500);
      }
    } catch (err) {
      showFeedback('Error completing consultation', 'error');
    } finally {
      setSaving(false);
    }
  };

  // ============ Vitals ============

  const handleSaveVitals = async () => {
    setSaving(true);
    try {
      const vitalsData = {
        blood_pressure: `${vitalsForm.blood_pressure_systolic}/${vitalsForm.blood_pressure_diastolic}`,
        heart_rate: vitalsForm.heart_rate, temperature: vitalsForm.temperature,
        weight: vitalsForm.weight, height: vitalsForm.height,
        respiratory_rate: vitalsForm.respiratory_rate, oxygen_saturation: vitalsForm.oxygen_saturation,
        bmi: vitalsForm.bmi
      };
      const res = await fetch('/api/patients/vitals', {
        method: 'POST', headers,
        body: JSON.stringify({ patient_id: patientUuid, vital_signs: JSON.stringify(vitalsData), notes: vitalsForm.notes })
      });
      if (res.ok) {
        showFeedback('Vitals recorded');
      } else {
        const err = await res.json().catch(() => ({}));
        showFeedback(err.detail || 'Failed to save vitals', 'error');
      }
    } catch (err) {
      showFeedback('Failed to save vitals', 'error');
    } finally {
      setSaving(false);
    }
  };

  // ============ Prescription ============

  const addMedication = () => {
    setPrescriptionForm(prev => ({
      ...prev,
      medications: [...prev.medications, { medicine_name: '', quantity_prescribed: 1, dosage: '', frequency_schedule: '1-0-0', food_timing: 'after_food', duration: '', instructions: '' }]
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

  const handleSavePrescription = async () => {
    const validMeds = prescriptionForm.medications.filter(m => m.medicine_name.trim());
    if (validMeds.length === 0) return;
    setSaving(true);
    try {
      const medicinesPayload = validMeds.map(m => ({
        name: m.medicine_name,
        dosage: m.dosage || 'As directed',
        duration: m.duration || 'As directed',
        instructions: m.instructions || null,
        quantity: m.quantity_prescribed ? String(m.quantity_prescribed) : null,
        frequency_schedule: m.frequency_schedule || '1-0-0',
        food_timing: m.food_timing || 'after_food'
      }));

      let res;
      if (currentPrescriptionId) {
        // Update existing prescription
        res = await fetch(`/api/prescriptions-simple/${currentPrescriptionId}`, {
          method: 'PUT', headers,
          body: JSON.stringify({
            medicines: medicinesPayload,
            diagnosis: prescriptionForm.diagnosis || null,
            notes: prescriptionForm.notes || null
          })
        });
      } else {
        // Create new prescription
        res = await fetch('/api/prescriptions-simple/', {
          method: 'POST', headers,
          body: JSON.stringify({
            patient_id: patientUuid,
            consultation_id: activeConsultation?.id || null,
            medicines: medicinesPayload,
            diagnosis: prescriptionForm.diagnosis || null,
            notes: prescriptionForm.notes || null
          })
        });
      }

      if (res.ok) {
        const data = await res.json();
        setCurrentPrescriptionId(data.prescription_id);
        setSavedPrescription(data);
        showFeedback(currentPrescriptionId ? 'Prescription updated' : 'Prescription created');
        fetchPatientPrescriptions();
        // Load PDF preview
        fetchRxPdf(data.prescription_id, rxIncludeHeader);
      } else {
        const err = await res.json();
        const detail = typeof err.detail === 'string' ? err.detail : 'Failed to save prescription';
        showFeedback(detail, 'error');
      }
    } catch (err) {
      showFeedback('Error saving prescription', 'error');
    } finally {
      setSaving(false);
    }
  };

  // ============ Lab Order ============

  const toggleLabTestSelection = (testId) => {
    setSelectedLabTests(prev => prev.includes(testId) ? prev.filter(id => id !== testId) : [...prev, testId]);
  };

  const addCustomLabTest = () => {
    const name = customLabTestInput.trim();
    if (name && !customLabTests.includes(name)) {
      setCustomLabTests(prev => [...prev, name]);
      setCustomLabTestInput('');
    }
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

  const handleSubmitLabOrder = async () => {
    if (selectedLabTests.length === 0 && customLabTests.length === 0) return;
    setSaving(true);
    try {
      let combinedNotes = labOrderNotes || '';
      if (customLabTests.length > 0) {
        const customNote = `Other tests requested: ${customLabTests.join(', ')}`;
        combinedNotes = combinedNotes ? `${combinedNotes}\n${customNote}` : customNote;
      }
      if (selectedLabTests.length > 0) {
        const res = await fetch('/api/lab/orders', {
          method: 'POST', headers,
          body: JSON.stringify({ patient_id: parseInt(patientId), test_ids: selectedLabTests, priority: labOrderPriority, notes: combinedNotes || null })
        });
        if (!res.ok) {
          const err = await res.json();
          showFeedback(typeof err.detail === 'string' ? err.detail : 'Failed to create lab orders', 'error');
          setSaving(false);
          return;
        }
      }
      showFeedback(`${selectedLabTests.length + customLabTests.length} lab order(s) created`);
      setSelectedLabTests([]);
      setCustomLabTests([]);
      setCustomLabTestInput('');
      setLabOrderNotes('');
      fetchPatientLabOrders();
    } catch (err) {
      showFeedback('Error creating lab orders', 'error');
    } finally {
      setSaving(false);
    }
  };

  // ============ Lab Results ============

  const openReport = async (reportId) => {
    if (expandedReport?.id === reportId) { setExpandedReport(null); return; }
    try {
      const res = await fetch(`/api/lab/reports/${reportId}`, { headers });
      if (res.ok) setExpandedReport(await res.json());
    } catch (err) {
      console.error('Failed to fetch report:', err);
    }
  };

  const downloadReport = async (reportId, orderNumber, includeHeader = true) => {
    try {
      const res = await fetch(`/api/lab/reports/${reportId}/download?include_header=${includeHeader}`, { headers });
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `lab_report_${orderNumber}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download:', err);
    }
  };

  // ============ Render ============

  // Auto-save current tab before switching
  const handleTabChange = async (newTab) => {
    if (newTab === activeTab) return;

    // Save current tab's data if it has content
    if (activeTab === 'vitals') {
      const hasVitals = vitalsForm.blood_pressure_systolic || vitalsForm.heart_rate ||
        vitalsForm.temperature || vitalsForm.weight || vitalsForm.height ||
        vitalsForm.oxygen_saturation || vitalsForm.respiratory_rate;
      if (hasVitals) {
        await handleSaveVitals();
      }
    } else if (activeTab === 'consultation') {
      const hasConsultation = consultationForm.chief_complaint || consultationForm.present_history ||
        consultationForm.examination_findings || consultationForm.notes;
      if (hasConsultation) {
        await handleSaveConsultation();
      }
    } else if (activeTab === 'prescription') {
      const hasValidMeds = prescriptionForm.medications.some(m => m.medicine_name.trim());
      if (hasValidMeds) {
        await handleSavePrescription();
      }
    } else if (activeTab === 'lab-order') {
      const hasLabOrder = selectedLabTests.length > 0 || customLabTests.length > 0;
      if (hasLabOrder) {
        await handleSubmitLabOrder();
      }
    }

    setActiveTab(newTab);
  };

  const frequencyOptions = [
    { value: '1-0-0', label: 'Morning only' },
    { value: '0-1-0', label: 'Afternoon only' },
    { value: '0-0-1', label: 'Night only' },
    { value: '1-0-1', label: 'Morning & Night' },
    { value: '1-1-0', label: 'Morning & Afternoon' },
    { value: '1-1-1', label: 'Three times a day' },
    { value: '0-1-1', label: 'Afternoon & Night' },
  ];

  return (
    <div className="space-y-4">
      {feedback.message && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white ${feedback.type === 'error' ? 'bg-red-500' : 'bg-green-500'}`}>
          {feedback.message}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Stethoscope className="h-6 w-6" />
            Consultation - {patientName}
          </h1>
          {appointment && (
            <p className="text-sm text-gray-500 mt-1">
              {appointment.appointment_type} | {appointment.appointment_date} | #{appointment.appointment_number}
            </p>
          )}
        </div>
        {activeConsultation && (
          <Badge className="bg-green-100 text-green-800">{activeConsultation.consultation_number}</Badge>
        )}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="vitals"><Activity className="h-4 w-4 mr-1" /> Vitals</TabsTrigger>
          <TabsTrigger value="consultation"><Stethoscope className="h-4 w-4 mr-1" /> Findings</TabsTrigger>
          <TabsTrigger value="prescription"><Pill className="h-4 w-4 mr-1" /> Prescription</TabsTrigger>
          <TabsTrigger value="lab-order"><TestTube className="h-4 w-4 mr-1" /> Lab Order</TabsTrigger>
          <TabsTrigger value="lab-results">
            <Eye className="h-4 w-4 mr-1" /> Lab Results
            {labOrders.filter(o => o.status === 'completed' && o.has_report).length > 0 && (
              <Badge className="ml-1 bg-green-500 text-white text-xs px-1.5">{labOrders.filter(o => o.status === 'completed' && o.has_report).length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="history" onClick={() => fetchConsultationHistory()}>
            <History className="h-4 w-4 mr-1" /> History
          </TabsTrigger>
        </TabsList>

        {/* ====== Vitals Tab ====== */}
        <TabsContent value="vitals">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <Label>BP Systolic (mmHg)</Label>
                  <Input type="number" value={vitalsForm.blood_pressure_systolic}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, blood_pressure_systolic: e.target.value }))} placeholder="120" />
                </div>
                <div>
                  <Label>BP Diastolic (mmHg)</Label>
                  <Input type="number" value={vitalsForm.blood_pressure_diastolic}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, blood_pressure_diastolic: e.target.value }))} placeholder="80" />
                </div>
                <div>
                  <Label>Heart Rate (bpm)</Label>
                  <Input type="number" value={vitalsForm.heart_rate}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, heart_rate: e.target.value }))} placeholder="72" />
                </div>
                <div>
                  <Label>Temperature (F)</Label>
                  <Input type="number" step="0.1" value={vitalsForm.temperature}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, temperature: e.target.value }))} placeholder="98.6" />
                </div>
                <div>
                  <Label>Weight (kg)</Label>
                  <Input type="number" step="0.1" value={vitalsForm.weight}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, weight: e.target.value }))} placeholder="70" />
                </div>
                <div>
                  <Label>Height (cm)</Label>
                  <Input type="number" value={vitalsForm.height}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, height: e.target.value }))} placeholder="170" />
                </div>
                <div>
                  <Label>SpO2 (%)</Label>
                  <Input type="number" value={vitalsForm.oxygen_saturation}
                    onChange={(e) => setVitalsForm(prev => ({ ...prev, oxygen_saturation: e.target.value }))} placeholder="98" />
                </div>
                <div>
                  <Label>BMI</Label>
                  <Input value={vitalsForm.bmi} readOnly className="bg-gray-50" placeholder="Auto" />
                </div>
              </div>
              <div>
                <Label>Vitals Notes</Label>
                <Textarea value={vitalsForm.notes} onChange={(e) => setVitalsForm(prev => ({ ...prev, notes: e.target.value }))}
                  placeholder="Any observations..." rows={2} />
              </div>
              <Button onClick={handleSaveVitals} disabled={saving}>
                <Save className="h-4 w-4 mr-1" /> Save Vitals
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ====== Findings Tab ====== */}
        <TabsContent value="consultation">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div>
                <Label>Chief Complaint *</Label>
                <Textarea value={consultationForm.chief_complaint}
                  onChange={(e) => setConsultationForm(prev => ({ ...prev, chief_complaint: e.target.value }))}
                  placeholder="Patient's primary complaint..." rows={2} />
              </div>
              <div>
                <Label>Present History</Label>
                <Textarea value={consultationForm.present_history}
                  onChange={(e) => setConsultationForm(prev => ({ ...prev, present_history: e.target.value }))}
                  placeholder="History of present illness, onset, duration..." rows={3} />
              </div>
              <div>
                <Label>Examination Findings</Label>
                <Textarea value={consultationForm.examination_findings}
                  onChange={(e) => setConsultationForm(prev => ({ ...prev, examination_findings: e.target.value }))}
                  placeholder="Physical examination findings..." rows={3} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Follow-up Date</Label>
                  <Input type="date" value={consultationForm.follow_up_date}
                    onChange={(e) => setConsultationForm(prev => ({ ...prev, follow_up_date: e.target.value }))} />
                </div>
                <div>
                  <Label>Notes</Label>
                  <Textarea value={consultationForm.notes}
                    onChange={(e) => setConsultationForm(prev => ({ ...prev, notes: e.target.value }))}
                    placeholder="Additional notes..." rows={2} />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <Button onClick={handleSaveConsultation} disabled={saving}>
                  <Save className="h-4 w-4 mr-1" /> {activeConsultation ? 'Update' : 'Save'} Findings
                </Button>
                {activeConsultation && activeConsultation.status === 'ongoing' && (
                  <Button className="bg-green-600 hover:bg-green-700" onClick={handleCompleteConsultation} disabled={saving}>
                    <CheckCircle className="h-4 w-4 mr-1" /> Complete Consultation
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ====== Prescription Tab ====== */}
        <TabsContent value="prescription">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div>
                <Label>Diagnosis</Label>
                <Input value={prescriptionForm.diagnosis}
                  onChange={(e) => setPrescriptionForm(prev => ({ ...prev, diagnosis: e.target.value }))}
                  placeholder="Enter diagnosis..." />
              </div>

              <div className="flex items-center justify-between">
                <Label className="text-base font-semibold">Medications</Label>
              </div>

              <div className="border rounded-lg overflow-hidden">
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
                    {prescriptionForm.medications.map((med, idx) => (
                        <tr key={idx} className="border-b last:border-0 hover:bg-gray-50/50">
                          <td className="px-2 py-2 text-gray-400 text-center">{idx + 1}</td>
                          <td className="px-2 py-2">
                            <Input value={med.medicine_name || ''} onChange={(e) => updateMedication(idx, 'medicine_name', e.target.value)}
                              placeholder="Medicine name" className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={med.dosage} onChange={(e) => updateMedication(idx, 'dosage', e.target.value)}
                              placeholder="1 tab" className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            <select value={med.frequency_schedule || '1-0-0'}
                              onChange={(e) => updateMedication(idx, 'frequency_schedule', e.target.value)}
                              className="w-full h-8 text-xs border border-gray-200 rounded px-1">
                              {frequencyOptions.map(opt => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          </td>
                          <td className="px-2 py-2">
                            <select value={med.food_timing || 'after_food'}
                              onChange={(e) => updateMedication(idx, 'food_timing', e.target.value)}
                              className="w-full h-8 text-xs border border-gray-200 rounded px-1">
                              <option value="before_food">Before food</option>
                              <option value="after_food">After food</option>
                              <option value="with_food">With food</option>
                              <option value="on_empty_stomach">Empty stomach</option>
                              <option value="anytime">Anytime</option>
                            </select>
                          </td>
                          <td className="px-2 py-2">
                            <Input value={med.duration} onChange={(e) => updateMedication(idx, 'duration', e.target.value)}
                              placeholder="7 days" className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={med.instructions} onChange={(e) => updateMedication(idx, 'instructions', e.target.value)}
                              placeholder="Notes..." className="h-8 text-sm" />
                          </td>
                          <td className="px-2 py-2">
                            {prescriptionForm.medications.length > 1 && (
                              <button type="button" onClick={() => removeMedication(idx)}
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

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Follow-up Date</Label>
                  <Input type="date" value={prescriptionForm.follow_up_date}
                    onChange={(e) => setPrescriptionForm(prev => ({ ...prev, follow_up_date: e.target.value }))} />
                </div>
                <div>
                  <Label>Prescription Notes</Label>
                  <Input value={prescriptionForm.notes}
                    onChange={(e) => setPrescriptionForm(prev => ({ ...prev, notes: e.target.value }))}
                    placeholder="Additional notes..." />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Button onClick={handleSavePrescription} disabled={saving}>
                  <Save className="h-4 w-4 mr-1" /> {currentPrescriptionId ? 'Update' : 'Save'} Prescription
                </Button>
                {savedPrescription && (
                  <Badge className="bg-green-100 text-green-700">
                    <CheckCircle className="h-3 w-3 mr-1" /> Saved — {savedPrescription.prescription_id}
                  </Badge>
                )}
              </div>

              {/* Saved Prescription Preview */}
              {savedPrescription && (
                <div className="mt-6 pt-4 border-t space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-sm flex items-center gap-2">
                      <FileText className="h-4 w-4" /> Prescription Preview
                    </h3>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 text-xs text-gray-600">
                        <input
                          type="checkbox"
                          checked={rxIncludeHeader}
                          onChange={(e) => {
                            setRxIncludeHeader(e.target.checked);
                            fetchRxPdf(savedPrescription.prescription_id, e.target.checked);
                          }}
                          className="rounded"
                        />
                        Include hospital letterhead
                      </label>
                      {rxPdfUrl && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => window.open(rxPdfUrl, '_blank')}>
                            <Eye className="h-3 w-3 mr-1" /> View
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => {
                            const a = document.createElement('a');
                            a.href = rxPdfUrl;
                            a.download = `prescription_${savedPrescription.prescription_id}.pdf`;
                            a.click();
                          }}>
                            <Printer className="h-3 w-3 mr-1" /> Download
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {rxPdfUrl ? (
                    <iframe src={rxPdfUrl} className="w-full h-[500px] border rounded-lg" title="Prescription PDF" />
                  ) : (
                    <div className="text-center py-8 text-gray-400">
                      <p className="text-sm">Loading prescription preview...</p>
                    </div>
                  )}
                </div>
              )}

            </CardContent>
          </Card>
        </TabsContent>

        {/* ====== Lab Order Tab ====== */}
        <TabsContent value="lab-order">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input placeholder="Search tests..." value={labSearchQuery}
                    onChange={(e) => setLabSearchQuery(e.target.value)} className="pl-10" />
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
                  <p className="text-sm text-blue-700 font-medium mb-1">{selectedLabTests.length + customLabTests.length} test(s) selected</p>
                  <div className="flex flex-wrap gap-1">
                    {selectedLabTests.map(id => {
                      const t = availableLabTests.find(t => t.id === id);
                      return t ? <Badge key={id} variant="secondary" className="cursor-pointer" onClick={() => toggleLabTestSelection(id)}>{t.name} x</Badge> : null;
                    })}
                    {customLabTests.map(name => (
                      <Badge key={name} variant="outline" className="cursor-pointer bg-orange-50 text-orange-700"
                        onClick={() => setCustomLabTests(prev => prev.filter(n => n !== name))}>{name} (custom) x</Badge>
                    ))}
                  </div>
                </div>
              )}

              <div className="border rounded-lg max-h-[250px] overflow-y-auto">
                {filteredLabTests.length === 0 ? (
                  <p className="text-center text-gray-500 py-6 text-sm">No tests available.</p>
                ) : filteredLabTests.map(test => (
                  <div key={test.id}
                    className={`flex items-center p-3 border-b last:border-0 cursor-pointer hover:bg-gray-50 ${selectedLabTests.includes(test.id) ? 'bg-blue-50' : ''}`}
                    onClick={() => toggleLabTestSelection(test.id)}>
                    <input type="checkbox" checked={selectedLabTests.includes(test.id)} readOnly className="rounded mr-3" />
                    <div>
                      <span className="font-medium text-sm">{test.name}</span>
                      <Badge variant="outline" className="text-xs ml-2">{test.test_code}</Badge>
                      <div className="text-xs text-gray-500">{test.category_name} | Rs. {test.cost}{test.sample_type && ` | ${test.sample_type}`}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="border rounded-lg p-3 space-y-2">
                <Label className="text-sm">Other (test not in list)</Label>
                <div className="flex gap-2">
                  <Input value={customLabTestInput}
                    onChange={(e) => setCustomLabTestInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomLabTest(); } }}
                    placeholder="Enter test name and press Enter" className="flex-1" />
                  <Button size="sm" variant="outline" onClick={addCustomLabTest} disabled={!customLabTestInput.trim()}>Add</Button>
                </div>
              </div>

              <div className="flex gap-3 items-end">
                <div>
                  <Label className="text-xs">Priority</Label>
                  <Select value={labOrderPriority} onValueChange={setLabOrderPriority}>
                    <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                      <SelectItem value="stat">STAT</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex-1">
                  <Label className="text-xs">Notes</Label>
                  <Input value={labOrderNotes} onChange={(e) => setLabOrderNotes(e.target.value)} placeholder="Clinical notes..." />
                </div>
                <Button onClick={handleSubmitLabOrder}
                  disabled={(selectedLabTests.length === 0 && customLabTests.length === 0) || saving}>
                  <TestTube className="h-4 w-4 mr-1" /> Order {selectedLabTests.length + customLabTests.length} Test(s)
                </Button>
              </div>

              {/* Pending orders */}
              {labOrders.filter(o => o.status !== 'completed' && o.status !== 'cancelled').length > 0 && (
                <div className="pt-4 border-t">
                  <h3 className="font-semibold text-sm text-gray-600 mb-2">Pending Orders</h3>
                  {labOrders.filter(o => o.status !== 'completed' && o.status !== 'cancelled').map(order => (
                    <div key={order.id} className="flex items-center justify-between p-2 border rounded mb-1 text-sm">
                      <span>{order.test_name} ({order.test_code})</span>
                      <Badge className={
                        order.status === 'processing' ? 'bg-purple-100 text-purple-700' :
                        order.status === 'collected' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-blue-100 text-blue-700'
                      }>{order.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ====== Lab Results Tab ====== */}
        <TabsContent value="lab-results">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-base">
                  <Eye className="h-5 w-5" /> Lab Results for {patientName}
                </span>
                <Button variant="outline" size="sm" onClick={fetchPatientLabOrders}>Refresh</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                const completedOrders = labOrders.filter(o => o.status === 'completed' && o.has_report);
                const pendingOrders = labOrders.filter(o => o.status !== 'completed' && o.status !== 'cancelled');

                if (completedOrders.length === 0 && pendingOrders.length === 0) {
                  return (
                    <div className="text-center py-8 text-gray-500">
                      <TestTube className="h-10 w-10 mx-auto mb-3 text-gray-300" />
                      <p>No lab results available for this patient yet.</p>
                    </div>
                  );
                }

                // Group completed orders by date
                const groupedByDate = {};
                completedOrders.forEach(order => {
                  const dateKey = order.order_date
                    ? format(new Date(order.order_date), 'yyyy-MM-dd')
                    : 'unknown';
                  if (!groupedByDate[dateKey]) groupedByDate[dateKey] = [];
                  groupedByDate[dateKey].push(order);
                });

                // Sort dates descending (most recent first)
                const sortedDates = Object.keys(groupedByDate).sort((a, b) => b.localeCompare(a));

                return (
                  <div className="space-y-4">
                    {/* Current pending orders */}
                    {pendingOrders.length > 0 && (
                      <div>
                        <h3 className="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-2">
                          <Clock className="h-4 w-4" /> Pending Orders
                        </h3>
                        <div className="space-y-1">
                          {pendingOrders.map(order => (
                            <div key={order.id} className="flex items-center justify-between p-2.5 border rounded-lg text-sm bg-amber-50/50">
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{order.test_name}</span>
                                <Badge variant="outline" className="text-xs">{order.test_code}</Badge>
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

                    {/* Completed results grouped by date */}
                    {completedOrders.length > 0 && (
                      <div>
                        {pendingOrders.length > 0 && (
                          <h3 className="text-sm font-semibold text-gray-600 mb-2 flex items-center gap-2">
                            <History className="h-4 w-4" /> Completed Results
                          </h3>
                        )}
                        <div className="space-y-1.5">
                          {sortedDates.map(dateKey => {
                            const orders = groupedByDate[dateKey];
                            const isExpanded = expandedLabGroups[dateKey];
                            const displayDate = dateKey !== 'unknown'
                              ? format(new Date(dateKey), 'dd MMM yyyy')
                              : 'Unknown date';
                            const abnormalCount = orders.reduce((sum, o) => {
                              // We'll show abnormal count if we have expanded data
                              return sum;
                            }, 0);

                            return (
                              <div key={dateKey} className="border rounded-lg overflow-hidden">
                                {/* Group header row */}
                                <div
                                  className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors"
                                  onClick={() => setExpandedLabGroups(prev => ({ ...prev, [dateKey]: !prev[dateKey] }))}
                                >
                                  {isExpanded
                                    ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                                    : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                                  }
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium text-gray-800">Consultation on {displayDate}</span>
                                      <Badge variant="outline" className="text-xs">{orders.length} test{orders.length !== 1 ? 's' : ''}</Badge>
                                      <Badge className="bg-green-100 text-green-700 text-xs">Completed</Badge>
                                    </div>
                                    {!isExpanded && (
                                      <p className="text-xs text-gray-500 mt-0.5 truncate">
                                        {orders.map(o => o.test_name).join(', ')}
                                      </p>
                                    )}
                                  </div>
                                </div>

                                {/* Expanded: show each test with results */}
                                {isExpanded && (
                                  <div className="border-t bg-gray-50">
                                    {orders.map((order, oIdx) => (
                                      <div key={order.id} className={oIdx > 0 ? 'border-t border-gray-200' : ''}>
                                        {/* Individual test header */}
                                        <div
                                          className="flex items-center justify-between px-4 py-2.5 cursor-pointer hover:bg-gray-100 transition-colors"
                                          onClick={() => openReport(order.report_id)}
                                        >
                                          <div className="flex items-center gap-2">
                                            <TestTube className="h-3.5 w-3.5 text-gray-400" />
                                            <span className="text-sm font-medium">{order.test_name}</span>
                                            <Badge variant="outline" className="text-[10px]">{order.test_code}</Badge>
                                          </div>
                                          <div className="flex items-center gap-2">
                                            <Button size="sm" variant="ghost" className="h-7 px-2" title="Download with header"
                                              onClick={(e) => { e.stopPropagation(); downloadReport(order.report_id, order.order_number, true); }}>
                                              <Printer className="h-3.5 w-3.5" />
                                            </Button>
                                            <Button size="sm" variant="ghost" className="h-7 px-2 text-gray-400" title="Download without header"
                                              onClick={(e) => { e.stopPropagation(); downloadReport(order.report_id, order.order_number, false); }}>
                                              <FileText className="h-3.5 w-3.5" />
                                            </Button>
                                            <Button size="sm" variant={expandedReport?.id === order.report_id ? 'default' : 'ghost'} className="h-7 px-2"
                                              onClick={(e) => { e.stopPropagation(); openReport(order.report_id); }}>
                                              {expandedReport?.id === order.report_id
                                                ? <ChevronDown className="h-3.5 w-3.5" />
                                                : <Eye className="h-3.5 w-3.5" />
                                              }
                                            </Button>
                                          </div>
                                        </div>

                                        {/* Inline results table */}
                                        {expandedReport && expandedReport.order_id === order.id && (
                                          <div className="px-4 pb-3">
                                            <table className="w-full text-sm">
                                              <thead>
                                                <tr className="border-b text-left text-gray-500">
                                                  <th className="pb-2 pr-3 text-xs font-medium">Parameter</th>
                                                  <th className="pb-2 pr-3 text-xs font-medium">Result</th>
                                                  <th className="pb-2 pr-3 text-xs font-medium">Unit</th>
                                                  <th className="pb-2 pr-3 text-xs font-medium">Reference</th>
                                                  <th className="pb-2 text-xs font-medium">Status</th>
                                                </tr>
                                              </thead>
                                              <tbody>
                                                {expandedReport.results?.map((r, idx) => (
                                                  <tr key={idx} className={`border-b last:border-0 ${r.is_abnormal ? 'bg-red-50' : ''}`}>
                                                    <td className="py-1.5 pr-3 font-medium">{r.parameter_name}</td>
                                                    <td className={`py-1.5 pr-3 ${r.is_abnormal ? 'text-red-600 font-bold' : ''}`}>{r.value}</td>
                                                    <td className="py-1.5 pr-3 text-gray-500">{r.unit || '-'}</td>
                                                    <td className="py-1.5 pr-3 text-gray-500 text-xs">
                                                      {r.reference_min != null || r.reference_max != null
                                                        ? `${r.reference_min ?? '–'} - ${r.reference_max ?? '–'}` : '-'}
                                                    </td>
                                                    <td className="py-1.5">
                                                      {r.is_abnormal ? (
                                                        <Badge variant="destructive" className="text-xs"><AlertCircle className="h-3 w-3 mr-0.5" />Abnormal</Badge>
                                                      ) : r.field_type === 'numeric' && (r.reference_min != null || r.reference_max != null) ? (
                                                        <Badge variant="secondary" className="text-xs">Normal</Badge>
                                                      ) : null}
                                                    </td>
                                                  </tr>
                                                ))}
                                              </tbody>
                                            </table>
                                            {expandedReport.interpretation && (
                                              <div className="mt-2 p-2 bg-white rounded border">
                                                <p className="text-xs font-medium text-gray-600">Interpretation</p>
                                                <p className="text-sm">{expandedReport.interpretation}</p>
                                              </div>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        </TabsContent>
        {/* ====== History Tab ====== */}
        <TabsContent value="history">
          <Card>
            <CardContent className="pt-6">
              {consultationHistory.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  <History className="h-10 w-10 mx-auto mb-3 opacity-50" />
                  <p className="text-sm">No previous consultations found</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {consultationHistory.map((consult) => {
                    const isExpanded = expandedHistoryItems[consult.id];
                    const consultDate = consult.consultation_date
                      ? format(new Date(consult.consultation_date), 'dd MMM yyyy, hh:mm a')
                      : 'Unknown date';

                    return (
                      <div key={consult.id} className="border rounded-lg overflow-hidden">
                        {/* Header row */}
                        <div
                          className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
                          onClick={() => setExpandedHistoryItems(prev => ({ ...prev, [consult.id]: !prev[consult.id] }))}
                        >
                          {isExpanded
                            ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                            : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                          }
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-medium text-gray-800">{consultDate}</span>
                              <Badge variant="outline" className="text-xs">{consult.consultation_type}</Badge>
                              <Badge className={
                                consult.status === 'completed' ? 'bg-green-100 text-green-700 text-xs' :
                                consult.status === 'ongoing' ? 'bg-blue-100 text-blue-700 text-xs' :
                                'bg-gray-100 text-gray-600 text-xs'
                              }>{consult.status}</Badge>
                            </div>
                            {consult.chief_complaint && (
                              <p className="text-xs text-gray-500 mt-0.5 truncate">
                                Chief Complaint: {consult.chief_complaint}
                              </p>
                            )}
                          </div>
                          <span className="text-xs text-gray-400 flex-shrink-0">{consult.doctor_name}</span>
                        </div>

                        {/* Expanded content */}
                        {isExpanded && (
                          <div className="border-t bg-gray-50 px-4 py-4 space-y-4">
                            {/* Consultation details */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              {consult.chief_complaint && (
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Chief Complaint</p>
                                  <p className="text-sm text-gray-800 mt-1">{consult.chief_complaint}</p>
                                </div>
                              )}
                              {consult.present_history && (
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">History</p>
                                  <p className="text-sm text-gray-800 mt-1">{consult.present_history}</p>
                                </div>
                              )}
                              {consult.examination_findings && (
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Examination Findings</p>
                                  <p className="text-sm text-gray-800 mt-1">{consult.examination_findings}</p>
                                </div>
                              )}
                              {consult.notes && (
                                <div>
                                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Notes</p>
                                  <p className="text-sm text-gray-800 mt-1">{consult.notes}</p>
                                </div>
                              )}
                            </div>

                            {/* Vitals */}
                            {consult.vital_signs && Object.keys(consult.vital_signs).length > 0 && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Vital Signs</p>
                                <div className="flex flex-wrap gap-3">
                                  {consult.vital_signs.blood_pressure && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">BP: {consult.vital_signs.blood_pressure}</span>
                                  )}
                                  {consult.vital_signs.heart_rate && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">HR: {consult.vital_signs.heart_rate} bpm</span>
                                  )}
                                  {consult.vital_signs.temperature && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">Temp: {consult.vital_signs.temperature}°F</span>
                                  )}
                                  {consult.vital_signs.weight && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">Wt: {consult.vital_signs.weight} kg</span>
                                  )}
                                  {consult.vital_signs.oxygen_saturation && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">SpO2: {consult.vital_signs.oxygen_saturation}%</span>
                                  )}
                                  {consult.vital_signs.respiratory_rate && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">RR: {consult.vital_signs.respiratory_rate}/min</span>
                                  )}
                                  {consult.vital_signs.bmi && (
                                    <span className="text-xs bg-white border rounded px-2 py-1">BMI: {consult.vital_signs.bmi}</span>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Prescriptions */}
                            {consult.prescriptions && consult.prescriptions.length > 0 && (
                              <div>
                                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Prescriptions</p>
                                {consult.prescriptions.map((rx, rxIdx) => (
                                  <div key={rxIdx} className="bg-white border rounded-lg p-3 mb-2">
                                    {rx.diagnosis && (
                                      <p className="text-xs text-gray-600 mb-2">Diagnosis: <span className="font-medium">{rx.diagnosis}</span></p>
                                    )}
                                    <div className="space-y-1.5">
                                      {rx.medicines?.map((m, mIdx) => (
                                        <div key={mIdx} className="flex items-start gap-2 text-sm">
                                          <span className="text-gray-400 mt-0.5 flex-shrink-0">{mIdx + 1}.</span>
                                          <div className="flex-1">
                                            <span className="font-medium text-gray-800">{m.name || m.medicine_name}</span>
                                            <div className="text-xs text-gray-500 mt-0.5 flex flex-wrap gap-x-3">
                                              {m.dosage && <span>Dosage: {m.dosage}</span>}
                                              {m.frequency_schedule && <span>Schedule: {m.frequency_schedule}</span>}
                                              {m.duration && <span>Duration: {m.duration}</span>}
                                              {m.food_timing && <span>{m.food_timing.replace(/_/g, ' ')}</span>}
                                              {m.quantity && <span>Qty: {m.quantity}</span>}
                                            </div>
                                            {m.instructions && <p className="text-xs text-gray-400 mt-0.5">{m.instructions}</p>}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                    {rx.notes && (
                                      <p className="text-xs text-gray-500 mt-2 pt-2 border-t">Notes: {rx.notes}</p>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Follow-up */}
                            {consult.follow_up_date && (
                              <p className="text-xs text-gray-500">
                                Follow-up: {format(new Date(consult.follow_up_date), 'dd MMM yyyy')}
                              </p>
                            )}
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
      </Tabs>
    </div>
  );
};

export default ConsultationPage;
