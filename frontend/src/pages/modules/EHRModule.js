import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import {
  Search, FileText, Activity, Pill, TestTube, User, Calendar, ArrowLeft,
  Phone, MapPin, Heart, Clock, ChevronDown, ChevronUp, Printer,
  Stethoscope, AlertCircle, CheckCircle, RefreshCw, Filter, Tag,
  ChevronLeft, ChevronRight, AlertTriangle, Bed, Receipt, Download,
  IndianRupee, CalendarDays, CalendarPlus, BedDouble, ShoppingBag, FileSpreadsheet
} from 'lucide-react';
import { format } from 'date-fns';
import { printPdfFromUrl } from '../../utils/printPdf';
import LabTestBookingDialog from '../../components/LabTestBookingDialog';
import PatientFileLabelDialog from '../../components/PatientFileLabelDialog';
import ReferralSelectWithCreate from '../../components/ReferralSelectWithCreate';
import EhrExportDialog from '../../components/EhrExportDialog';
import { useToast } from '../../hooks/use-toast';
import { applyDobToForm, formatPatientAge } from '../../utils/patientAge';

const EMPTY_EDIT_FORM = {
  first_name: '', last_name: '', date_of_birth: '', age: '', age_months: '', gender: '',
  blood_group: '', marital_status: '', abha_id: '', gstin: '', email: '', referred_by: '',
  emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
  address_line1: '', address_line2: '', village: '', mandal: '', district: '',
};

const EHRModule = () => (
  <Routes>
    <Route index element={<EHRPage />} />
    <Route path="patient/:patientId" element={<EHRPage />} />
  </Routes>
);

const EHRPage = () => {
  const { patientId: routePatientId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [allPatients, setAllPatients] = useState([]);
  const [displayedPatients, setDisplayedPatients] = useState([]);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [patientHistory, setPatientHistory] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState('timeline');
  const [expandedItems, setExpandedItems] = useState({});
  const [currentPage, setCurrentPage] = useState(1);
  const [enabledModules, setEnabledModules] = useState({});
  const [showLabBooking, setShowLabBooking] = useState(false);
  const [labBookingPatient, setLabBookingPatient] = useState(null);
  const [showExcelExport, setShowExcelExport] = useState(false);
  const [filterGender, setFilterGender] = useState('all');
  const [filterBloodGroup, setFilterBloodGroup] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [fileLabelPatientId, setFileLabelPatientId] = useState(null);
  const [fileLabelContext, setFileLabelContext] = useState({ source: 'reprint' });
  const [showEditPatientDialog, setShowEditPatientDialog] = useState(false);
  const [editPatientForm, setEditPatientForm] = useState(EMPTY_EDIT_FORM);
  const [editLoading, setEditLoading] = useState(false);
  const [referralList, setReferralList] = useState([]);
  const patientsPerPage = 10;

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Load all patients on mount
  useEffect(() => {
    fetchAllPatients();
  }, []);

  useEffect(() => {
    fetch('/api/system/enabled-modules', { headers })
      .then((res) => (res.ok ? res.json() : []))
      .then((mods) => {
        const map = {};
        (mods || []).forEach((m) => { map[m.module_name] = m.is_enabled; });
        setEnabledModules(map);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetch('/api/referrals', { headers })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setReferralList(data || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filter/sort patients when search or filters change
  useEffect(() => {
    let list = allPatients;
    if (filterGender && filterGender !== 'all') {
      list = list.filter((p) => (p.gender || '') === filterGender);
    }
    if (filterBloodGroup && filterBloodGroup !== 'all') {
      list = list.filter((p) => (p.blood_group || '') === filterBloodGroup);
    }
    if (!searchQuery.trim()) {
      setDisplayedPatients(list);
      setCurrentPage(1);
      return;
    }
    const q = searchQuery.toLowerCase();
    const matched = [];
    const unmatched = [];
    for (const p of list) {
      const name = (p.full_name || `${p.first_name} ${p.last_name}`).toLowerCase();
      const phone = (p.primary_phone || '').toLowerCase();
      const mrn = (p.mrn || '').toLowerCase();
      const pid = (p.patient_id || '').toLowerCase();
      if (name.includes(q) || phone.includes(q) || mrn.includes(q) || pid.includes(q)) {
        matched.push(p);
      } else {
        unmatched.push(p);
      }
    }
    setDisplayedPatients([...matched, ...unmatched]);
    setCurrentPage(1);
  }, [searchQuery, allPatients, filterGender, filterBloodGroup]);

  const loadPatientHistory = useCallback(async (patientUuid) => {
    if (!patientUuid) return;
    setLoadingHistory(true);
    setPatientHistory(null);
    setActiveTab('timeline');
    setExpandedItems({});
    try {
      const res = await fetch(`/api/ehr/patient/${patientUuid}/history`, { headers });
      if (res.ok) {
        const data = await res.json();
        setPatientHistory(data);
        setSelectedPatient(data.patient);
      } else {
        setSelectedPatient(null);
        setPatientHistory(null);
      }
    } catch (err) {
      console.error('Failed to load history:', err);
      setSelectedPatient(null);
      setPatientHistory(null);
    } finally {
      setLoadingHistory(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Deep-link / route: open patient detail when URL has patientId
  useEffect(() => {
    if (routePatientId) {
      loadPatientHistory(routePatientId);
    } else {
      setSelectedPatient(null);
      setPatientHistory(null);
      setLoadingHistory(false);
    }
  }, [routePatientId, loadPatientHistory]);

  const fetchAllPatients = async () => {
    setLoadingPatients(true);
    try {
      const res = await fetch('/api/ehr/patients/search?q=&limit=200', { headers });
      if (res.ok) {
        const data = await res.json();
        setAllPatients(data);
        setDisplayedPatients(data);
      }
    } catch (err) {
      console.error('Failed to load patients:', err);
    } finally {
      setLoadingPatients(false);
    }
  };

  const selectPatient = (patient) => {
    const uuid = patient.patient_id;
    if (!uuid) return;
    setSearchQuery('');
    navigate(`/dashboard/ehr/patient/${encodeURIComponent(uuid)}`);
  };

  const goBackToList = () => {
    navigate('/dashboard/ehr');
  };

  const clearFilters = () => {
    setSearchQuery('');
    setFilterGender('all');
    setFilterBloodGroup('all');
    setCurrentPage(1);
  };

  const openEditPatient = async (patient) => {
    if (!patient?.patient_id) return;
    setEditLoading(true);
    try {
      const res = await fetch(`/api/patients/${patient.patient_id}`, { headers });
      if (!res.ok) throw new Error('Failed to load patient');
      const data = await res.json();
      setSelectedPatient(data);
      setEditPatientForm({
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        date_of_birth: data.date_of_birth || '',
        age: data.age != null ? String(data.age) : '',
        age_months: data.age_months != null ? String(data.age_months) : '',
        gender: data.gender || '',
        blood_group: data.blood_group || '',
        marital_status: data.marital_status || '',
        abha_id: data.abha_id || '',
        gstin: data.gstin || '',
        email: data.email || '',
        referred_by: data.referred_by || '',
        emergency_contact_name: data.emergency_contact_name || '',
        emergency_contact_phone: data.emergency_contact_phone || '',
        emergency_contact_relation: data.emergency_contact_relation || '',
        address_line1: data.address_line1 || '',
        address_line2: data.address_line2 || '',
        village: data.village || '',
        mandal: data.mandal || '',
        district: data.district || '',
      });
      setShowEditPatientDialog(true);
    } catch (err) {
      console.error(err);
      toast({ title: 'Error', description: 'Failed to load patient for editing', variant: 'destructive' });
    } finally {
      setEditLoading(false);
    }
  };

  const handleUpdatePatient = async () => {
    if (!selectedPatient?.patient_id) return;
    setEditLoading(true);
    try {
      const updateData = {};
      Object.entries(editPatientForm).forEach(([key, value]) => {
        if (value !== '' && value !== null && value !== undefined) {
          updateData[key] = ['age', 'age_months'].includes(key) ? parseInt(value, 10) : value;
        }
      });
      const res = await fetch(`/api/patients/${selectedPatient.patient_id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(updateData),
      });
      if (res.ok) {
        toast({ title: 'Success', description: 'Patient updated successfully!' });
        setShowEditPatientDialog(false);
        fetchAllPatients();
      } else {
        const err = await res.json().catch(() => ({}));
        toast({
          title: 'Update Failed',
          description: typeof err.detail === 'string' ? err.detail : 'Failed to update patient',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Error updating patient:', error);
      toast({ title: 'Error', description: 'Error updating patient', variant: 'destructive' });
    } finally {
      setEditLoading(false);
    }
  };

  const bookAppointment = (patient) => {
    const uuid = patient?.patient_id || patientHistory?.patient?.patient_id;
    if (!uuid) return;
    navigate(`/dashboard/reception/appointments?action=schedule&patientUuid=${encodeURIComponent(uuid)}`);
  };

  const admitPatient = (patient) => {
    const uuid = patient?.patient_id || patientHistory?.patient?.patient_id;
    if (!uuid) return;
    navigate(`/dashboard/inpatient/admissions?action=admit&patientUuid=${encodeURIComponent(uuid)}`);
  };

  const toggleExpand = (key) => {
    setExpandedItems(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try { return format(new Date(dateStr), 'dd MMM yyyy'); } catch { return dateStr; }
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '—';
    try { return format(new Date(dateStr), 'dd MMM yyyy, hh:mm a'); } catch { return dateStr; }
  };

  const downloadPrescription = async (prescriptionId) => {
    try {
      const res = await fetch(`/api/prescriptions-simple/${prescriptionId}/download`, { headers });
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `prescription_${prescriptionId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const downloadLabReport = async (reportId, orderNumber) => {
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
      console.error('Download failed:', err);
    }
  };

  // Generic download for an aggregated document (prescription / lab report / discharge summary)
  const downloadDocument = async (doc) => {
    try {
      const res = await fetch(doc.download_url, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(doc.label || 'document').replace(/[^a-z0-9]+/gi, '_')}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Document download failed:', err);
    }
  };

  const formatMoney = (amount) => {
    const n = Number(amount || 0);
    return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const billStatusColor = (status) => {
    const map = {
      paid: 'bg-green-100 text-green-700',
      partial: 'bg-yellow-100 text-yellow-700',
      pending: 'bg-orange-100 text-orange-700',
      cancelled: 'bg-red-100 text-red-700',
    };
    return map[status] || 'bg-gray-100 text-gray-600';
  };

  const severityColor = (severity) => {
    const map = {
      mild: 'bg-yellow-100 text-yellow-700',
      moderate: 'bg-orange-100 text-orange-700',
      severe: 'bg-red-100 text-red-700',
      anaphylaxis: 'bg-red-600 text-white',
    };
    return map[severity] || 'bg-gray-100 text-gray-600';
  };

  const statusColor = (status) => {
    const map = {
      active: 'bg-green-100 text-green-700',
      completed: 'bg-blue-100 text-blue-700',
      ongoing: 'bg-yellow-100 text-yellow-700',
      cancelled: 'bg-red-100 text-red-700',
      resolved: 'bg-gray-100 text-gray-600',
      chronic: 'bg-orange-100 text-orange-700',
      ordered: 'bg-blue-100 text-blue-700',
      collected: 'bg-yellow-100 text-yellow-700',
      processing: 'bg-purple-100 text-purple-700',
      admitted: 'bg-blue-100 text-blue-700',
      discharged: 'bg-green-100 text-green-700',
      scheduled: 'bg-indigo-100 text-indigo-700',
      checked_in: 'bg-yellow-100 text-yellow-700',
      voided: 'bg-red-100 text-red-700',
    };
    return map[status] || 'bg-gray-100 text-gray-600';
  };

  const typeIcon = (type) => {
    if (type === 'consultation') return <Stethoscope className="h-4 w-4" />;
    if (type === 'prescription') return <Pill className="h-4 w-4" />;
    if (type === 'lab_order') return <TestTube className="h-4 w-4" />;
    if (type === 'appointment') return <CalendarDays className="h-4 w-4" />;
    if (type === 'admission') return <Bed className="h-4 w-4" />;
    if (type === 'pharmacy_sale') return <ShoppingBag className="h-4 w-4" />;
    if (type === 'physio_session') return <Activity className="h-4 w-4" />;
    return <FileText className="h-4 w-4" />;
  };

  const typeColor = (type) => {
    if (type === 'consultation') return 'border-l-blue-500 bg-blue-50/30';
    if (type === 'prescription') return 'border-l-green-500 bg-green-50/30';
    if (type === 'lab_order') return 'border-l-purple-500 bg-purple-50/30';
    if (type === 'appointment') return 'border-l-indigo-500 bg-indigo-50/30';
    if (type === 'admission') return 'border-l-teal-500 bg-teal-50/30';
    if (type === 'pharmacy_sale') return 'border-l-amber-500 bg-amber-50/30';
    if (type === 'physio_session') return 'border-l-cyan-500 bg-cyan-50/30';
    return 'border-l-gray-500';
  };

  const typeLabel = (type) => {
    if (type === 'consultation') return 'Consultation';
    if (type === 'prescription') return 'Prescription';
    if (type === 'lab_order') return 'Lab Order';
    if (type === 'appointment') return 'Appointment';
    if (type === 'admission') return 'Admission';
    if (type === 'pharmacy_sale') return 'Pharmacy';
    if (type === 'physio_session') return 'Physio Session';
    return type;
  };

  const typeBadgeClass = (type) => {
    if (type === 'consultation') return 'bg-blue-100 text-blue-600';
    if (type === 'prescription') return 'bg-green-100 text-green-600';
    if (type === 'lab_order') return 'bg-purple-100 text-purple-600';
    if (type === 'appointment') return 'bg-indigo-100 text-indigo-600';
    if (type === 'admission') return 'bg-teal-100 text-teal-600';
    if (type === 'pharmacy_sale') return 'bg-amber-100 text-amber-600';
    if (type === 'physio_session') return 'bg-cyan-100 text-cyan-600';
    return 'bg-gray-100 text-gray-600';
  };

  // ============ Render Helpers ============

  const renderVitals = (vitals) => {
    if (!vitals || !Object.values(vitals).some(v => v)) return null;
    const items = [];
    if (vitals.blood_pressure) items.push({ label: 'BP', value: `${vitals.blood_pressure} mmHg` });
    if (vitals.heart_rate) items.push({ label: 'HR', value: `${vitals.heart_rate} bpm` });
    if (vitals.temperature) items.push({ label: 'Temp', value: `${vitals.temperature}°F` });
    if (vitals.spo2 || vitals.oxygen_saturation) items.push({ label: 'SpO2', value: `${vitals.spo2 || vitals.oxygen_saturation}%` });
    if (vitals.respiratory_rate) items.push({ label: 'RR', value: `${vitals.respiratory_rate}/min` });
    if (vitals.weight) items.push({ label: 'Wt', value: `${vitals.weight} kg` });
    if (vitals.height) items.push({ label: 'Ht', value: `${vitals.height} cm` });
    if (vitals.bmi) items.push({ label: 'BMI', value: vitals.bmi });
    if (items.length === 0) return null;

    return (
      <div className="flex flex-wrap gap-3 mt-2">
        {items.map((item, i) => (
          <span key={i} className="text-xs bg-gray-100 rounded px-2 py-1">
            <span className="font-medium text-gray-500">{item.label}:</span> {item.value}
          </span>
        ))}
      </div>
    );
  };

  const renderConsultationCard = (c, key) => {
    const isExpanded = expandedItems[key];
    return (
      <div key={key} className="space-y-2">
        <div className="flex items-center justify-between cursor-pointer" onClick={() => toggleExpand(key)}>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{c.chief_complaint || 'Consultation'}</span>
              <Badge className={`text-xs ${statusColor(c.status)}`}>{c.status}</Badge>
              <Badge variant="outline" className="text-xs">{c.consultation_type}</Badge>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">{c.doctor_name}{c.doctor_specialization ? ` (${c.doctor_specialization})` : ''} | {c.consultation_number}</p>
          </div>
          {isExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
        </div>

        {isExpanded && (
          <div className="pl-2 space-y-3 text-sm border-l-2 border-gray-200 ml-1">
            {c.vital_signs && renderVitals(c.vital_signs)}

            {c.chief_complaint && (
              <div><span className="text-xs font-medium text-gray-500">Chief Complaint:</span><p className="text-sm">{c.chief_complaint}</p></div>
            )}
            {c.present_history && (
              <div><span className="text-xs font-medium text-gray-500">Present History:</span><p className="text-sm">{c.present_history}</p></div>
            )}
            {c.examination_findings && (
              <div><span className="text-xs font-medium text-gray-500">Examination Findings:</span><p className="text-sm">{c.examination_findings}</p></div>
            )}

            {c.diagnoses && c.diagnoses.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-500">Diagnoses:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {c.diagnoses.map((d, i) => (
                    <Badge key={i} variant="outline" className="text-xs">
                      {d.diagnosis_name} {d.diagnosis_code && `(${d.diagnosis_code})`}
                      {d.severity && ` - ${d.severity}`}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {c.treatment_plans && c.treatment_plans.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-500">Treatment Plans:</span>
                {c.treatment_plans.map((t, i) => (
                  <p key={i} className="text-xs mt-0.5">{t.treatment_type}: {t.description}</p>
                ))}
              </div>
            )}

            {c.follow_up_date && (
              <div className="text-xs"><span className="font-medium text-gray-500">Follow-up:</span> {formatDate(c.follow_up_date)}</div>
            )}

            {c.notes && (
              <div><span className="text-xs font-medium text-gray-500">Notes:</span><p className="text-xs text-gray-600">{c.notes}</p></div>
            )}

            {c.medical_notes && c.medical_notes.length > 0 && (
              <div>
                <span className="text-xs font-medium text-gray-500">Medical Notes:</span>
                {c.medical_notes.map((n, i) => (
                  <div key={i} className="text-xs mt-1 bg-gray-50 rounded p-2">
                    <span className="font-medium">{n.title || n.note_type}</span>
                    <p className="text-gray-600 mt-0.5">{n.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderPrescriptionCard = (rx, key) => {
    const isExpanded = expandedItems[key];
    return (
      <div key={key} className="space-y-2">
        <div className="flex items-center justify-between cursor-pointer" onClick={() => toggleExpand(key)}>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{rx.diagnosis || 'Prescription'}</span>
              <Badge className={`text-xs ${statusColor(rx.status)}`}>{rx.status}</Badge>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              {rx.doctor_name} | {rx.prescription_id} | {rx.medicines?.length || 0} medicine(s)
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="Download prescription" onClick={(e) => { e.stopPropagation(); downloadPrescription(rx.prescription_id); }}>
              <Printer className="h-3.5 w-3.5" />
            </Button>
            {isExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
          </div>
        </div>

        {isExpanded && (
          <div className="pl-2 border-l-2 border-gray-200 ml-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-1 pr-2">#</th>
                  <th className="pb-1 pr-2">Medicine</th>
                  <th className="pb-1 pr-2">Dosage</th>
                  <th className="pb-1 pr-2">Duration</th>
                  <th className="pb-1">Instructions</th>
                </tr>
              </thead>
              <tbody>
                {(rx.medicines || []).map((m, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1 pr-2">{i + 1}</td>
                    <td className="py-1 pr-2 font-medium">{m.name || m.medicine_name}</td>
                    <td className="py-1 pr-2">{m.dosage}{m.frequency_schedule ? ` (${m.frequency_schedule})` : ''}</td>
                    <td className="py-1 pr-2">{m.duration}</td>
                    <td className="py-1 text-gray-500">{m.instructions || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rx.notes && <p className="text-xs text-gray-500 mt-2">Notes: {rx.notes}</p>}
          </div>
        )}
      </div>
    );
  };

  const renderLabOrderCard = (lo, key) => {
    const isExpanded = expandedItems[key];
    return (
      <div key={key} className="space-y-2">
        <div className="flex items-center justify-between cursor-pointer" onClick={() => toggleExpand(key)}>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{lo.test_name}</span>
              <Badge className={`text-xs ${statusColor(lo.status)}`}>{lo.status}</Badge>
              {lo.priority !== 'normal' && <Badge variant="destructive" className="text-xs">{lo.priority}</Badge>}
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              {lo.test_code} | {lo.order_number}{lo.doctor_name ? ` | ${lo.doctor_name}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-1">
            {lo.report && (
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" title="Download report" onClick={(e) => { e.stopPropagation(); downloadLabReport(lo.report.id, lo.order_number); }}>
                <Printer className="h-3.5 w-3.5" />
              </Button>
            )}
            {isExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
          </div>
        </div>

        {isExpanded && lo.report && (
          <div className="pl-2 border-l-2 border-gray-200 ml-1">
            {lo.report.results && lo.report.results.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-1 pr-2">Parameter</th>
                    <th className="pb-1 pr-2">Result</th>
                    <th className="pb-1 pr-2">Unit</th>
                    <th className="pb-1">Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {lo.report.results.map((r, i) => (
                    <tr key={i} className={`border-b last:border-0 ${r.is_abnormal ? 'bg-red-50' : ''}`}>
                      <td className="py-1 pr-2 font-medium">{r.parameter_name}</td>
                      <td className={`py-1 pr-2 ${r.is_abnormal ? 'text-red-600 font-bold' : ''}`}>{r.value}</td>
                      <td className="py-1 pr-2 text-gray-500">{r.unit || '—'}</td>
                      <td className="py-1 text-gray-500">{r.reference_range || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {lo.report.interpretation && (
              <div className="mt-2 text-xs bg-gray-50 rounded p-2">
                <span className="font-medium text-gray-500">Interpretation:</span>
                <p className="text-gray-700 mt-0.5">{lo.report.interpretation}</p>
              </div>
            )}
            {lo.report.is_verified && (
              <div className="flex items-center gap-1 mt-1 text-xs text-green-600">
                <CheckCircle className="h-3 w-3" /> Verified
              </div>
            )}
          </div>
        )}

        {isExpanded && !lo.report && lo.status !== 'completed' && (
          <p className="text-xs text-gray-400 pl-2 ml-1 border-l-2 border-gray-200">Results pending...</p>
        )}
      </div>
    );
  };

  // ============ Main Render ============

  const showPatientDetail = Boolean(routePatientId);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {showPatientDetail && (
            <Button variant="ghost" size="sm" onClick={goBackToList}>
              <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
          )}
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" /> Electronic Health Records
          </h1>
        </div>
        {patientHistory && !loadingHistory && (
          <div className="flex items-center gap-2 flex-wrap">
            {enabledModules.outpatient && (
              <Button size="sm" onClick={() => bookAppointment()}>
                <CalendarPlus className="h-4 w-4 mr-1" /> Book Appointment
              </Button>
            )}
            {enabledModules.inpatient && (
              <Button size="sm" variant="outline" onClick={() => admitPatient()}>
                <BedDouble className="h-4 w-4 mr-1" /> Admit
              </Button>
            )}
            {enabledModules.lab && (
              <Button size="sm" variant="outline" onClick={() => {
                setLabBookingPatient(patientHistory?.patient || null);
                setShowLabBooking(true);
              }}>
                <TestTube className="h-4 w-4 mr-1" /> Book Lab
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setShowExcelExport(true)}>
              <FileSpreadsheet className="h-4 w-4 mr-1" /> Export Excel
            </Button>
          </div>
        )}
      </div>

      {/* Patient Search + Full List */}
      {!showPatientDetail && (
        <>
          <div className="flex justify-between items-center flex-wrap gap-3">
            <div>
              <p className="text-gray-600">Search patients and open their clinical chart</p>
            </div>
            <Button onClick={fetchAllPatients} variant="outline" className="flex items-center space-x-2">
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </Button>
          </div>

          <Card>
            <CardContent className="p-6">
              <div className="flex flex-col lg:flex-row gap-4">
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <Input
                      placeholder="Search name, phone, MRN, or scan barcode…"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => setShowFilters(!showFilters)}
                    className="flex items-center space-x-2"
                  >
                    <Filter className="h-4 w-4" />
                    <span>Filters</span>
                  </Button>
                  {(searchQuery || (filterGender && filterGender !== 'all') || (filterBloodGroup && filterBloodGroup !== 'all')) && (
                    <Button variant="outline" onClick={clearFilters}>
                      Clear
                    </Button>
                  )}
                </div>
              </div>

              {showFilters && (
                <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="filterGender">Gender</Label>
                      <Select value={filterGender} onValueChange={setFilterGender}>
                        <SelectTrigger>
                          <SelectValue placeholder="All Genders" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Genders</SelectItem>
                          <SelectItem value="Male">Male</SelectItem>
                          <SelectItem value="Female">Female</SelectItem>
                          <SelectItem value="Other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="filterBloodGroup">Blood Group</Label>
                      <Select value={filterBloodGroup} onValueChange={setFilterBloodGroup}>
                        <SelectTrigger>
                          <SelectValue placeholder="All Blood Groups" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Blood Groups</SelectItem>
                          <SelectItem value="A+">A+</SelectItem>
                          <SelectItem value="A-">A-</SelectItem>
                          <SelectItem value="B+">B+</SelectItem>
                          <SelectItem value="B-">B-</SelectItem>
                          <SelectItem value="AB+">AB+</SelectItem>
                          <SelectItem value="AB-">AB-</SelectItem>
                          <SelectItem value="O+">O+</SelectItem>
                          <SelectItem value="O-">O-</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Patients ({displayedPatients.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingPatients ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                  <span>Loading patients...</span>
                </div>
              ) : displayedPatients.length === 0 ? (
                <div className="text-center py-8">
                  <User className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500">
                    {searchQuery || filterGender !== 'all' || filterBloodGroup !== 'all'
                      ? 'No patients found matching your criteria'
                      : 'No patients found'}
                  </p>
                </div>
              ) : (
                <>
                  <div className="text-xs text-gray-500 mb-2">
                    Showing {Math.min((currentPage - 1) * patientsPerPage + 1, displayedPatients.length)}–{Math.min(currentPage * patientsPerPage, displayedPatients.length)} of {displayedPatients.length} patients
                  </div>
                  <div className="overflow-x-auto border rounded-lg">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="border-b bg-gray-50 text-left">
                          <th className="py-2.5 px-3 font-medium text-gray-600">Patient</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">MRN</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">Age</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">Gender</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">Phone</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">Blood</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600">Address</th>
                          <th className="py-2.5 px-3 font-medium text-gray-600 text-right min-w-[320px]">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayedPatients
                          .slice((currentPage - 1) * patientsPerPage, currentPage * patientsPerPage)
                          .map((p) => (
                            <tr key={p.patient_id} className="border-b hover:bg-gray-50">
                              <td className="py-3 px-3">
                                <div className="flex items-center gap-2">
                                  <User className="h-4 w-4 text-gray-400 shrink-0" />
                                  <span className="font-semibold">
                                    {p.full_name || `${p.first_name} ${p.last_name}`}
                                  </span>
                                </div>
                              </td>
                              <td className="py-3 px-3 text-gray-700 whitespace-nowrap">{p.mrn || '—'}</td>
                              <td className="py-3 px-3 text-gray-600 whitespace-nowrap">
                                {p.date_of_birth || p.age != null || p.age_months != null
                                  ? formatPatientAge(p)
                                  : '—'}
                              </td>
                              <td className="py-3 px-3">
                                {p.gender ? <Badge variant="outline">{p.gender}</Badge> : '—'}
                              </td>
                              <td className="py-3 px-3 text-gray-700 whitespace-nowrap">
                                <div className="flex items-center gap-1.5">
                                  <Phone className="h-3.5 w-3.5 text-gray-400" />
                                  {p.primary_phone || '—'}
                                </div>
                              </td>
                              <td className="py-3 px-3">
                                {p.blood_group ? <Badge variant="secondary">{p.blood_group}</Badge> : '—'}
                              </td>
                              <td className="py-3 px-3 text-gray-600 max-w-[180px] truncate" title={p.address || ''}>
                                {p.address || '—'}
                              </td>
                              <td className="py-3 px-3">
                                <div className="flex flex-wrap justify-end gap-1.5">
                                  <Button size="sm" variant="outline" onClick={() => selectPatient(p)}>
                                    View Chart
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={editLoading}
                                    onClick={() => openEditPatient(p)}
                                  >
                                    Edit
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setFileLabelContext({ source: 'reprint' });
                                      setFileLabelPatientId(p.id);
                                    }}
                                  >
                                    <Tag className="h-3.5 w-3.5 mr-1" />
                                    File label
                                  </Button>
                                  {enabledModules.outpatient && (
                                    <Button size="sm" onClick={() => bookAppointment(p)}>
                                      Book Appointment
                                    </Button>
                                  )}
                                  {enabledModules.lab && (
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => {
                                        setLabBookingPatient(p);
                                        setShowLabBooking(true);
                                      }}
                                    >
                                      Book Lab Test
                                    </Button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>

                  {Math.ceil(displayedPatients.length / patientsPerPage) > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <Button
                        variant="outline" size="sm"
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage((prev) => prev - 1)}
                      >
                        <ChevronLeft className="h-4 w-4 mr-1" /> Previous
                      </Button>
                      <div className="flex items-center gap-1">
                        {Array.from({ length: Math.ceil(displayedPatients.length / patientsPerPage) }, (_, i) => i + 1)
                          .filter((page) => page === 1 || page === Math.ceil(displayedPatients.length / patientsPerPage) || Math.abs(page - currentPage) <= 2)
                          .map((page, idx, arr) => (
                            <React.Fragment key={page}>
                              {idx > 0 && arr[idx - 1] !== page - 1 && <span className="px-1 text-gray-400">...</span>}
                              <Button
                                variant={currentPage === page ? 'default' : 'outline'}
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={() => setCurrentPage(page)}
                              >
                                {page}
                              </Button>
                            </React.Fragment>
                          ))}
                      </div>
                      <Button
                        variant="outline" size="sm"
                        disabled={currentPage >= Math.ceil(displayedPatients.length / patientsPerPage)}
                        onClick={() => setCurrentPage((prev) => prev + 1)}
                      >
                        Next <ChevronRight className="h-4 w-4 ml-1" />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Loading */}
      {showPatientDetail && loadingHistory && (
        <div className="text-center py-12 text-gray-500">
          <Activity className="h-8 w-8 mx-auto mb-2 animate-spin" />
          <p>Loading patient history...</p>
        </div>
      )}

      {showPatientDetail && !loadingHistory && !patientHistory && (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <AlertCircle className="h-10 w-10 mx-auto mb-2 text-gray-300" />
            <p>Patient record could not be loaded.</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={goBackToList}>
              Back to patient list
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Patient History View */}
      {patientHistory && !loadingHistory && (
        <>
          {/* Allergy Alert Banner */}
          {(patientHistory.allergies || []).some(a => a.is_active) && (
            <div className="rounded-lg border-l-4 border-red-500 bg-red-50 p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-700">Allergy Alert</p>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {patientHistory.allergies.filter(a => a.is_active).map(a => (
                      <Badge key={a.id} className={`text-xs ${severityColor(a.severity)}`}>
                        {a.allergen}{a.severity ? ` (${a.severity})` : ''}{a.reaction ? ` — ${a.reaction}` : ''}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Patient Info Card */}
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-start gap-4">
                <div className="h-14 w-14 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                  <User className="h-7 w-7 text-blue-600" />
                </div>
                <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <p className="text-lg font-bold">{patientHistory.patient.full_name}</p>
                    <p className="text-xs text-gray-500">MRN: {patientHistory.patient.mrn || '—'}</p>
                  </div>
                  <div className="text-sm space-y-0.5">
                    <p className="flex items-center gap-1 text-gray-600">
                      <Calendar className="h-3.5 w-3.5" />
                      {patientHistory.patient.age ? `${patientHistory.patient.age} yrs` : '—'} | {patientHistory.patient.gender || '—'}
                    </p>
                    <p className="flex items-center gap-1 text-gray-600">
                      <Heart className="h-3.5 w-3.5" />
                      Blood Group: {patientHistory.patient.blood_group || '—'}
                    </p>
                  </div>
                  <div className="text-sm space-y-0.5">
                    <p className="flex items-center gap-1 text-gray-600">
                      <Phone className="h-3.5 w-3.5" />
                      {patientHistory.patient.primary_phone}
                    </p>
                    {patientHistory.patient.emergency_contact_phone && (
                      <p className="flex items-center gap-1 text-gray-500 text-xs">
                        <AlertCircle className="h-3 w-3" />
                        Emergency: {patientHistory.patient.emergency_contact_phone}
                      </p>
                    )}
                  </div>
                  <div className="text-sm">
                    {patientHistory.patient.address && (
                      <p className="flex items-center gap-1 text-gray-600 text-xs">
                        <MapPin className="h-3.5 w-3.5 shrink-0" />
                        {patientHistory.patient.address}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Medical History */}
              {patientHistory.medical_history.length > 0 && (
                <div className="mt-4 pt-3 border-t">
                  <p className="text-xs font-semibold text-gray-500 mb-2">MEDICAL HISTORY</p>
                  <div className="flex flex-wrap gap-2">
                    {patientHistory.medical_history.map(mh => (
                      <Badge key={mh.id} className={`text-xs ${statusColor(mh.status)}`}>
                        {mh.condition}
                        {mh.status && ` (${mh.status})`}
                        {mh.diagnosed_date && ` - ${formatDate(mh.diagnosed_date)}`}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary Stats */}
              <div className="mt-4 pt-3 border-t grid grid-cols-3 md:grid-cols-7 gap-4">
                <div className="text-center">
                  <p className="text-2xl font-bold text-indigo-600">{patientHistory.summary?.visit_count ?? 0}</p>
                  <p className="text-xs text-gray-500">Visits</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-blue-600">{patientHistory.consultations.length}</p>
                  <p className="text-xs text-gray-500">Consultations</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-green-600">{patientHistory.prescriptions.length}</p>
                  <p className="text-xs text-gray-500">Prescriptions</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-purple-600">{patientHistory.lab_orders.length}</p>
                  <p className="text-xs text-gray-500">Lab Orders</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-amber-600">{(patientHistory.pharmacy_sales || []).length}</p>
                  <p className="text-xs text-gray-500">Pharmacy</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-700">{formatMoney(patientHistory.billing?.total_billed)}</p>
                  <p className="text-xs text-gray-500">Billed to Date</p>
                </div>
                <div className="text-center">
                  <p className={`text-2xl font-bold ${(patientHistory.billing?.outstanding || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {formatMoney(patientHistory.billing?.outstanding)}
                  </p>
                  <p className="text-xs text-gray-500">Outstanding</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-4 md:grid-cols-8 h-auto gap-1">
              <TabsTrigger value="timeline"><Clock className="h-4 w-4 mr-1" /> Timeline</TabsTrigger>
              <TabsTrigger value="visits"><CalendarDays className="h-4 w-4 mr-1" /> Visits</TabsTrigger>
              <TabsTrigger value="consultations"><Stethoscope className="h-4 w-4 mr-1" /> Consultations</TabsTrigger>
              <TabsTrigger value="prescriptions"><Pill className="h-4 w-4 mr-1" /> Prescriptions</TabsTrigger>
              <TabsTrigger value="lab"><TestTube className="h-4 w-4 mr-1" /> Lab</TabsTrigger>
              <TabsTrigger value="pharmacy"><ShoppingBag className="h-4 w-4 mr-1" /> Pharmacy</TabsTrigger>
              <TabsTrigger value="billing"><Receipt className="h-4 w-4 mr-1" /> Billing</TabsTrigger>
              <TabsTrigger value="documents"><FileText className="h-4 w-4 mr-1" /> Documents</TabsTrigger>
            </TabsList>

            {/* Timeline Tab */}
            <TabsContent value="timeline">
              <Card>
                <CardContent className="pt-4">
                  {patientHistory.timeline.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <FileText className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No records found for this patient.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {patientHistory.timeline.map((item, idx) => {
                        const key = `timeline-${item.type}-${idx}`;
                        return (
                          <div key={key} className={`border-l-4 rounded-lg border p-3 ${typeColor(item.type)}`}>
                            <div className="flex items-center gap-2 mb-2">
                              <span className={`p-1 rounded ${typeBadgeClass(item.type)}`}>
                                {typeIcon(item.type)}
                              </span>
                              <Badge variant="outline" className="text-xs">{typeLabel(item.type)}</Badge>
                              <span className="text-xs text-gray-500 ml-auto">{formatDateTime(item.date)}</span>
                            </div>

                            {item.type === 'consultation' && renderConsultationCard(item.data, key)}
                            {item.type === 'prescription' && renderPrescriptionCard(item.data, key)}
                            {item.type === 'lab_order' && renderLabOrderCard(item.data, key)}
                            {item.type === 'appointment' && (
                              <div className="text-sm space-y-1">
                                <p className="font-medium">{item.data.doctor_name}</p>
                                <p className="text-xs text-gray-500">{item.data.appointment_number}</p>
                                <div className="flex gap-2">
                                  <Badge className={`text-xs ${statusColor(item.data.status)}`}>{item.data.status}</Badge>
                                  <Badge className={`text-xs ${billStatusColor(item.data.payment_status)}`}>{item.data.payment_status}</Badge>
                                  <span className="text-xs text-gray-600 ml-auto">{formatMoney(item.data.final_amount)}</span>
                                </div>
                              </div>
                            )}
                            {item.type === 'admission' && (
                              <div className="text-sm space-y-1">
                                <p className="font-medium">{item.data.admission_number} · {item.data.admission_type}</p>
                                <p className="text-xs text-gray-500">{item.data.doctor_name}{item.data.bed_number ? ` · Bed ${item.data.bed_number}` : ''}</p>
                                <Badge className={`text-xs ${statusColor(item.data.status)}`}>{item.data.status}</Badge>
                              </div>
                            )}
                            {item.type === 'pharmacy_sale' && (
                              <div className="text-sm space-y-1">
                                <p className="font-medium">{item.data.sale_number}</p>
                                <p className="text-xs text-gray-500">{item.data.doctor_name || 'Walk-in'} · {item.data.payment_type}</p>
                                <div className="flex gap-2 items-center">
                                  <Badge className={`text-xs ${statusColor(item.data.status)}`}>{item.data.status}</Badge>
                                  <span className="text-xs text-gray-600 ml-auto">{formatMoney(item.data.grand_total)}</span>
                                </div>
                              </div>
                            )}
                            {item.type === 'physio_session' && (
                              <div className="text-sm space-y-1">
                                <p className="font-medium">
                                  {item.data.service_name || item.data.session_type} · {item.data.appointment_number}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {item.data.therapist_name}
                                  {item.data.appointment_time ? ` · ${item.data.appointment_time}` : ''}
                                </p>
                                {item.data.session_note && (
                                  <p className="text-xs text-gray-600">{item.data.session_note}</p>
                                )}
                                <Badge className={`text-xs ${statusColor(item.data.status)}`}>{item.data.status}</Badge>
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

            {/* Visits Tab */}
            <TabsContent value="visits">
              <div className="space-y-4">
                {/* Appointments */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <CalendarDays className="h-4 w-4" /> Appointments ({(patientHistory.appointments || []).length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(patientHistory.appointments || []).length === 0 ? (
                      <p className="text-sm text-gray-400 py-4 text-center">No appointments found.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-2 pr-2">Date</th>
                            <th className="pb-2 pr-2">Number</th>
                            <th className="pb-2 pr-2">Doctor</th>
                            <th className="pb-2 pr-2">Status</th>
                            <th className="pb-2 pr-2">Payment</th>
                            <th className="pb-2 text-right">Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {patientHistory.appointments.map(ap => (
                            <tr key={ap.id} className="border-b last:border-0">
                              <td className="py-2 pr-2">{formatDate(ap.appointment_date)}</td>
                              <td className="py-2 pr-2 text-gray-600">{ap.appointment_number}</td>
                              <td className="py-2 pr-2">{ap.doctor_name}</td>
                              <td className="py-2 pr-2"><Badge className={`text-xs ${statusColor(ap.status)}`}>{ap.status}</Badge></td>
                              <td className="py-2 pr-2"><Badge className={`text-xs ${billStatusColor(ap.payment_status)}`}>{ap.payment_status}</Badge></td>
                              <td className="py-2 text-right">{formatMoney(ap.final_amount)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </CardContent>
                </Card>

                {/* Admissions */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Bed className="h-4 w-4" /> Admissions ({(patientHistory.admissions || []).length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(patientHistory.admissions || []).length === 0 ? (
                      <p className="text-sm text-gray-400 py-4 text-center">No admissions found.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-2 pr-2">Admitted</th>
                            <th className="pb-2 pr-2">Discharged</th>
                            <th className="pb-2 pr-2">Number</th>
                            <th className="pb-2 pr-2">Type</th>
                            <th className="pb-2 pr-2">Bed</th>
                            <th className="pb-2 pr-2">Doctor</th>
                            <th className="pb-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {patientHistory.admissions.map(adm => (
                            <tr key={adm.id} className="border-b last:border-0">
                              <td className="py-2 pr-2">{formatDate(adm.admission_date)}</td>
                              <td className="py-2 pr-2">{adm.discharge_date ? formatDate(adm.discharge_date) : '—'}</td>
                              <td className="py-2 pr-2 text-gray-600">{adm.admission_number}</td>
                              <td className="py-2 pr-2 capitalize">{adm.admission_type}</td>
                              <td className="py-2 pr-2">{adm.bed_number || '—'}</td>
                              <td className="py-2 pr-2">{adm.doctor_name}</td>
                              <td className="py-2"><Badge className={`text-xs ${statusColor(adm.status)}`}>{adm.status}</Badge></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* Consultations Tab */}
            <TabsContent value="consultations">
              <Card>
                <CardContent className="pt-4">
                  {patientHistory.consultations.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <Stethoscope className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No consultations found.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {patientHistory.consultations.map((c, idx) => {
                        const key = `cons-${c.id}`;
                        return (
                          <div key={key} className="border rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs text-gray-500">{formatDateTime(c.consultation_date)}</span>
                            </div>
                            {renderConsultationCard(c, key)}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Prescriptions Tab */}
            <TabsContent value="prescriptions">
              <Card>
                <CardContent className="pt-4">
                  {patientHistory.prescriptions.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <Pill className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No prescriptions found.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {patientHistory.prescriptions.map((rx, idx) => {
                        const key = `rx-${rx.id}`;
                        return (
                          <div key={key} className="border rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs text-gray-500">{formatDateTime(rx.prescription_date)}</span>
                            </div>
                            {renderPrescriptionCard(rx, key)}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Lab Tab */}
            <TabsContent value="lab">
              <Card>
                <CardContent className="pt-4">
                  {patientHistory.lab_orders.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <TestTube className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No lab orders found.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {patientHistory.lab_orders.map((lo, idx) => {
                        const key = `lab-${lo.id}`;
                        return (
                          <div key={key} className="border rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs text-gray-500">{formatDateTime(lo.order_date)}</span>
                            </div>
                            {renderLabOrderCard(lo, key)}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Pharmacy Tab */}
            <TabsContent value="pharmacy">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <ShoppingBag className="h-4 w-4" /> Pharmacy Sales ({(patientHistory.pharmacy_sales || []).length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {(patientHistory.pharmacy_sales || []).length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <ShoppingBag className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No pharmacy sales found for this patient.</p>
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-2 pr-2">Date</th>
                          <th className="pb-2 pr-2">Sale No.</th>
                          <th className="pb-2 pr-2">Doctor</th>
                          <th className="pb-2 pr-2">Payment</th>
                          <th className="pb-2 pr-2">Status</th>
                          <th className="pb-2 text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {patientHistory.pharmacy_sales.map((s) => (
                          <tr key={s.id} className="border-b last:border-0">
                            <td className="py-2 pr-2">{formatDateTime(s.sale_date)}</td>
                            <td className="py-2 pr-2 text-gray-600">{s.sale_number}</td>
                            <td className="py-2 pr-2">{s.doctor_name || '—'}</td>
                            <td className="py-2 pr-2 capitalize">{s.payment_type || '—'}{s.billing_mode === 'inpatient_bill' ? ' (IP bill)' : ''}</td>
                            <td className="py-2 pr-2"><Badge className={`text-xs ${statusColor(s.status)}`}>{s.status}</Badge></td>
                            <td className="py-2 text-right">{formatMoney(s.grand_total)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Billing Tab */}
            <TabsContent value="billing">
              <div className="space-y-4">
                {/* Summary cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardContent className="pt-4 flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
                        <IndianRupee className="h-5 w-5 text-gray-600" />
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Total Billed</p>
                        <p className="text-xl font-bold">{formatMoney(patientHistory.billing?.total_billed)}</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center">
                        <CheckCircle className="h-5 w-5 text-green-600" />
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Total Paid</p>
                        <p className="text-xl font-bold text-green-600">{formatMoney(patientHistory.billing?.total_paid)}</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 flex items-center gap-3">
                      <div className={`h-10 w-10 rounded-full flex items-center justify-center ${(patientHistory.billing?.outstanding || 0) > 0 ? 'bg-red-100' : 'bg-gray-100'}`}>
                        <AlertCircle className={`h-5 w-5 ${(patientHistory.billing?.outstanding || 0) > 0 ? 'text-red-600' : 'text-gray-500'}`} />
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Outstanding</p>
                        <p className={`text-xl font-bold ${(patientHistory.billing?.outstanding || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {formatMoney(patientHistory.billing?.outstanding)}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Bill list */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Receipt className="h-4 w-4" /> Bills ({(patientHistory.billing?.bills || []).length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(patientHistory.billing?.bills || []).length === 0 ? (
                      <div className="text-center py-8 text-gray-500">
                        <Receipt className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                        <p>No bills found for this patient.</p>
                      </div>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-500 border-b">
                            <th className="pb-2 pr-2">Date</th>
                            <th className="pb-2 pr-2">Bill No.</th>
                            <th className="pb-2 pr-2">Type</th>
                            <th className="pb-2 pr-2 text-right">Amount</th>
                            <th className="pb-2 pr-2 text-right">Paid</th>
                            <th className="pb-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {patientHistory.billing.bills.map(b => (
                            <tr key={b.id} className="border-b last:border-0">
                              <td className="py-2 pr-2">{formatDate(b.bill_date)}</td>
                              <td className="py-2 pr-2 text-gray-600">{b.bill_number}</td>
                              <td className="py-2 pr-2 capitalize">{b.bill_type}{b.bill_subtype && b.bill_subtype !== 'final' ? ` (${b.bill_subtype})` : ''}</td>
                              <td className="py-2 pr-2 text-right">{formatMoney(b.total_amount)}</td>
                              <td className="py-2 pr-2 text-right">{formatMoney(b.amount_paid)}</td>
                              <td className="py-2"><Badge className={`text-xs ${billStatusColor(b.status)}`}>{b.status}</Badge></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* Documents Tab */}
            <TabsContent value="documents">
              <Card>
                <CardContent className="pt-4">
                  {(patientHistory.documents || []).length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <FileText className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                      <p>No documents found for this patient.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {patientHistory.documents.map((doc, idx) => (
                        <div key={`doc-${idx}`} className="flex items-center justify-between border rounded-lg p-3 hover:bg-gray-50">
                          <div className="flex items-center gap-3">
                            <span className={`p-2 rounded ${doc.type === 'prescription' ? 'bg-green-100 text-green-600' : doc.type === 'lab_report' ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600'}`}>
                              {doc.type === 'prescription' ? <Pill className="h-4 w-4" /> : doc.type === 'lab_report' ? <TestTube className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                            </span>
                            <div>
                              <p className="text-sm font-medium">{doc.label}</p>
                              <p className="text-xs text-gray-500">{formatDate(doc.date)}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title="View / Print"
                              onClick={() => printPdfFromUrl(doc.download_url)}>
                              <Printer className="h-4 w-4" />
                            </Button>
                            <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title="Download"
                              onClick={() => downloadDocument(doc)}>
                              <Download className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}

      <LabTestBookingDialog
        open={showLabBooking}
        onClose={(booked) => {
          setShowLabBooking(false);
          setLabBookingPatient(null);
          if (booked && routePatientId) loadPatientHistory(routePatientId);
        }}
        patient={labBookingPatient || patientHistory?.patient || null}
        referralList={referralList}
        onReferralsChange={setReferralList}
      />

      <PatientFileLabelDialog
        open={!!fileLabelPatientId}
        patientId={fileLabelPatientId}
        context={fileLabelContext}
        onClose={() => setFileLabelPatientId(null)}
      />

      <Dialog open={showEditPatientDialog} onOpenChange={setShowEditPatientDialog}>
        <DialogContent className="max-w-6xl w-[96vw] max-h-[90vh] flex flex-col overflow-hidden gap-0 p-0">
          <div className="shrink-0 border-b px-6 pt-5 pb-3">
            <DialogHeader className="space-y-0">
              <DialogTitle>
                Edit Patient - {selectedPatient?.first_name} {selectedPatient?.last_name}
              </DialogTitle>
            </DialogHeader>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-3 gap-y-2">
              <div>
                <Label>First Name *</Label>
                <Input
                  value={editPatientForm.first_name}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, first_name: e.target.value })}
                />
              </div>
              <div>
                <Label>Last Name *</Label>
                <Input
                  value={editPatientForm.last_name}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, last_name: e.target.value })}
                />
              </div>
              <div>
                <Label>Date of Birth</Label>
                <Input
                  type="date"
                  value={editPatientForm.date_of_birth}
                  onChange={(e) => setEditPatientForm((prev) => applyDobToForm(prev, e.target.value))}
                />
              </div>
              <div>
                <Label>Age (years)</Label>
                <Input
                  type="number"
                  min="0"
                  max="150"
                  placeholder="Years"
                  value={editPatientForm.age}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, age: e.target.value, date_of_birth: '' })}
                />
              </div>
              <div>
                <Label>Age (months)</Label>
                <Input
                  type="number"
                  min="0"
                  max="11"
                  placeholder="Months (for infants)"
                  value={editPatientForm.age_months}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, age_months: e.target.value, date_of_birth: '' })}
                />
              </div>
              <div>
                <Label>Gender</Label>
                <Select
                  value={editPatientForm.gender || 'none'}
                  onValueChange={(value) => setEditPatientForm({ ...editPatientForm, gender: value === 'none' ? '' : value })}
                >
                  <SelectTrigger><SelectValue placeholder="Select Gender" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    <SelectItem value="Male">Male</SelectItem>
                    <SelectItem value="Female">Female</SelectItem>
                    <SelectItem value="Other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Blood Group</Label>
                <Select
                  value={editPatientForm.blood_group || 'none'}
                  onValueChange={(value) => setEditPatientForm({ ...editPatientForm, blood_group: value === 'none' ? '' : value })}
                >
                  <SelectTrigger><SelectValue placeholder="Select Blood Group" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    <SelectItem value="A+">A+</SelectItem>
                    <SelectItem value="A-">A-</SelectItem>
                    <SelectItem value="B+">B+</SelectItem>
                    <SelectItem value="B-">B-</SelectItem>
                    <SelectItem value="AB+">AB+</SelectItem>
                    <SelectItem value="AB-">AB-</SelectItem>
                    <SelectItem value="O+">O+</SelectItem>
                    <SelectItem value="O-">O-</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Marital Status</Label>
                <Select
                  value={editPatientForm.marital_status || 'none'}
                  onValueChange={(value) => setEditPatientForm({ ...editPatientForm, marital_status: value === 'none' ? '' : value })}
                >
                  <SelectTrigger><SelectValue placeholder="Select Status" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    <SelectItem value="Single">Single</SelectItem>
                    <SelectItem value="Married">Married</SelectItem>
                    <SelectItem value="Widowed">Widowed</SelectItem>
                    <SelectItem value="Divorced">Divorced</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>ABHA ID</Label>
                <Input
                  value={editPatientForm.abha_id}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, abha_id: e.target.value })}
                  placeholder="14-digit ABHA number"
                />
              </div>
              <div>
                <Label>GSTIN (optional)</Label>
                <Input
                  value={editPatientForm.gstin || ''}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, gstin: e.target.value.toUpperCase() })}
                  placeholder="Customer GSTIN"
                  maxLength={15}
                />
              </div>
              <div>
                <Label>Email</Label>
                <Input
                  type="email"
                  value={editPatientForm.email}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, email: e.target.value })}
                  placeholder="patient@email.com"
                />
              </div>
              <ReferralSelectWithCreate
                value={editPatientForm.referred_by || ''}
                onValueChange={(name) => setEditPatientForm({ ...editPatientForm, referred_by: name })}
                referrals={referralList}
                onReferralsChange={setReferralList}
              />

              <div className="col-span-full border-t pt-2 mt-1">
                <Label className="text-sm font-semibold text-gray-700">Emergency Contact</Label>
              </div>
              <div>
                <Label>Contact Name</Label>
                <Input
                  value={editPatientForm.emergency_contact_name}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, emergency_contact_name: e.target.value })}
                />
              </div>
              <div>
                <Label>Contact Phone</Label>
                <Input
                  value={editPatientForm.emergency_contact_phone}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, emergency_contact_phone: e.target.value })}
                />
              </div>
              <div>
                <Label>Relation</Label>
                <Select
                  value={editPatientForm.emergency_contact_relation || 'none'}
                  onValueChange={(value) => setEditPatientForm({ ...editPatientForm, emergency_contact_relation: value === 'none' ? '' : value })}
                >
                  <SelectTrigger><SelectValue placeholder="Select Relation" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    <SelectItem value="Spouse">Spouse</SelectItem>
                    <SelectItem value="Parent">Parent</SelectItem>
                    <SelectItem value="Child">Child</SelectItem>
                    <SelectItem value="Sibling">Sibling</SelectItem>
                    <SelectItem value="Friend">Friend</SelectItem>
                    <SelectItem value="Other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-full border-t pt-2 mt-1">
                <Label className="text-sm font-semibold text-gray-700">Address</Label>
              </div>
              <div className="md:col-span-2 lg:col-span-3 xl:col-span-2">
                <Label>Address Line 1</Label>
                <Input
                  value={editPatientForm.address_line1}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, address_line1: e.target.value })}
                />
              </div>
              <div className="md:col-span-2 lg:col-span-3 xl:col-span-2">
                <Label>Address Line 2</Label>
                <Input
                  value={editPatientForm.address_line2}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, address_line2: e.target.value })}
                />
              </div>
              <div>
                <Label>Village / Town</Label>
                <Input
                  value={editPatientForm.village}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, village: e.target.value })}
                />
              </div>
              <div>
                <Label>Mandal / Taluka</Label>
                <Input
                  value={editPatientForm.mandal}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, mandal: e.target.value })}
                />
              </div>
              <div>
                <Label>District</Label>
                <Input
                  value={editPatientForm.district}
                  onChange={(e) => setEditPatientForm({ ...editPatientForm, district: e.target.value })}
                />
              </div>
            </div>
          </div>
          <div className="shrink-0 border-t px-6 py-3 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <Button variant="outline" onClick={() => setShowEditPatientDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdatePatient}
              disabled={editLoading || !editPatientForm.first_name || !editPatientForm.last_name || !editPatientForm.age}
            >
              {editLoading ? 'Updating...' : 'Update Patient'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <EhrExportDialog
        open={showExcelExport}
        onClose={() => setShowExcelExport(false)}
        patientUuid={patientHistory?.patient?.patient_id || routePatientId}
        patientName={patientHistory?.patient?.full_name}
        headers={headers}
      />

    </div>
  );
};

export default EHRModule;
