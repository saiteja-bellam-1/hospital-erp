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
  Clock, User, AlertCircle, Eye, Plus, Trash2, Save, Printer, Search
} from 'lucide-react';
import { format } from 'date-fns';
import axios from 'axios';

const ConsultationPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const appointmentId = searchParams.get('appointmentId');
  const patientId = searchParams.get('patientId');
  const patientUuid = searchParams.get('patientUuid') || '';
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

  // Appointment info
  const [appointment, setAppointment] = useState(null);

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
      await fetch('/api/patients/vitals', {
        method: 'POST', headers,
        body: JSON.stringify({ patient_id: patientUuid, vital_signs: JSON.stringify(vitalsData), notes: vitalsForm.notes })
      });
      showFeedback('Vitals recorded');
    } catch (err) {
      showFeedback('Vitals recorded (demo)');
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
      const res = await fetch('/api/prescriptions-simple/', {
        method: 'POST', headers,
        body: JSON.stringify({
          patient_id: patientUuid,
          consultation_id: null,
          medicines: validMeds.map(m => ({
            name: m.medicine_name,
            dosage: m.dosage || 'As directed',
            duration: m.duration || 'As directed',
            instructions: m.instructions || null,
            quantity: m.quantity_prescribed ? String(m.quantity_prescribed) : null,
            frequency_schedule: m.frequency_schedule || '1-0-0',
            food_timing: m.food_timing || 'after_food'
          })),
          diagnosis: prescriptionForm.diagnosis || null,
          notes: prescriptionForm.notes || null
        })
      });
      if (res.ok) {
        showFeedback('Prescription created');
        fetchPatientPrescriptions();
        setPrescriptionForm({
          medications: [{ medicine_name: '', quantity_prescribed: 1, dosage: '', frequency_schedule: '1-0-0', food_timing: 'after_food', duration: '', instructions: '' }],
          diagnosis: '', notes: '', follow_up_date: ''
        });
      } else {
        const err = await res.json();
        const detail = typeof err.detail === 'string' ? err.detail : 'Failed to create prescription';
        showFeedback(detail, 'error');
      }
    } catch (err) {
      showFeedback('Error creating prescription', 'error');
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

  const downloadReport = async (reportId, orderNumber) => {
    try {
      const res = await fetch(`/api/lab/reports/${reportId}/download`, { headers });
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
        <TabsList className="grid w-full grid-cols-5">
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
                <Button size="sm" variant="outline" onClick={addMedication}>
                  <Plus className="h-3 w-3 mr-1" /> Add Medicine
                </Button>
              </div>

              {prescriptionForm.medications.map((med, idx) => (
                <div key={idx} className="border rounded-lg p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-500">Medicine #{idx + 1}</span>
                    {prescriptionForm.medications.length > 1 && (
                      <Button size="sm" variant="ghost" className="text-red-500 h-6" onClick={() => removeMedication(idx)}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="col-span-2">
                      <Label className="text-xs">Medicine Name *</Label>
                      <Input value={med.medicine_name} onChange={(e) => updateMedication(idx, 'medicine_name', e.target.value)}
                        placeholder="Medicine name" />
                    </div>
                    <div>
                      <Label className="text-xs">Dosage</Label>
                      <Input value={med.dosage} onChange={(e) => updateMedication(idx, 'dosage', e.target.value)}
                        placeholder="e.g. 500mg" />
                    </div>
                    <div>
                      <Label className="text-xs">Duration</Label>
                      <Input value={med.duration} onChange={(e) => updateMedication(idx, 'duration', e.target.value)}
                        placeholder="e.g. 5 days" />
                    </div>
                    <div>
                      <Label className="text-xs">Schedule</Label>
                      <Select value={med.frequency_schedule} onValueChange={(v) => updateMedication(idx, 'frequency_schedule', v)}>
                        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {frequencyOptions.map(opt => (
                            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs">Food Timing</Label>
                      <Select value={med.food_timing} onValueChange={(v) => updateMedication(idx, 'food_timing', v)}>
                        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="before_food">Before food</SelectItem>
                          <SelectItem value="after_food">After food</SelectItem>
                          <SelectItem value="with_food">With food</SelectItem>
                          <SelectItem value="on_empty_stomach">Empty stomach</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-2">
                      <Label className="text-xs">Instructions</Label>
                      <Input value={med.instructions} onChange={(e) => updateMedication(idx, 'instructions', e.target.value)}
                        placeholder="Special instructions..." />
                    </div>
                  </div>
                </div>
              ))}

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

              <Button onClick={handleSavePrescription} disabled={saving}>
                <Save className="h-4 w-4 mr-1" /> Save Prescription
              </Button>

              {/* Previous prescriptions */}
              {prescriptions.length > 0 && (
                <div className="mt-6 pt-4 border-t">
                  <h3 className="font-semibold text-sm text-gray-600 mb-3">Previous Prescriptions</h3>
                  {prescriptions.slice(0, 5).map((rx, idx) => (
                    <div key={idx} className="text-sm border rounded p-2 mb-2">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{rx.prescription_number}</span>
                        <span className="text-xs text-gray-500">{rx.prescription_date && format(new Date(rx.prescription_date), 'dd MMM yyyy')}</span>
                      </div>
                      {rx.diagnosis && <p className="text-xs text-gray-600 mt-1">Dx: {rx.diagnosis}</p>}
                      <div className="text-xs text-gray-500 mt-1">
                        {rx.medicines?.map((m, i) => m.name || m.medicine_name).join(', ')}
                      </div>
                    </div>
                  ))}
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
              {labOrders.filter(o => o.status === 'completed' && o.has_report).length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <TestTube className="h-10 w-10 mx-auto mb-3 text-gray-300" />
                  <p>No lab results available for this patient yet.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {labOrders.filter(o => o.status === 'completed' && o.has_report).map(order => (
                    <div key={order.id} className="border rounded-lg">
                      <div className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50"
                        onClick={() => openReport(order.report_id)}>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{order.test_name}</span>
                            <Badge variant="outline" className="text-xs">{order.test_code}</Badge>
                            <Badge className="bg-green-100 text-green-700 text-xs">Completed</Badge>
                          </div>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {order.order_date && format(new Date(order.order_date), 'dd MMM yyyy, hh:mm a')} | #{order.order_number}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); downloadReport(order.report_id, order.order_number); }}>
                            <Printer className="h-4 w-4" />
                          </Button>
                          <Button size="sm" variant={expandedReport?.id === order.report_id ? 'default' : 'outline'}
                            onClick={(e) => { e.stopPropagation(); openReport(order.report_id); }}>
                            <Eye className="h-4 w-4 mr-1" /> {expandedReport?.id === order.report_id ? 'Hide' : 'View'}
                          </Button>
                        </div>
                      </div>

                      {expandedReport && expandedReport.order_id === order.id && (
                        <div className="border-t p-3 bg-gray-50">
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
                            <div className="mt-3 p-2 bg-white rounded border">
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
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ConsultationPage;
