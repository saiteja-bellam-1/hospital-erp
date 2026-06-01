import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import {
  Search, FileText, Activity, Pill, TestTube, User, Calendar, ArrowLeft,
  Phone, MapPin, Heart, Clock, ChevronDown, ChevronUp, Printer,
  Stethoscope, ClipboardList, AlertCircle, CheckCircle, Eye,
  ChevronLeft, ChevronRight
} from 'lucide-react';
import { format } from 'date-fns';

const EHRModule = () => {
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
  const patientsPerPage = 10;

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Load all patients on mount
  useEffect(() => {
    fetchAllPatients();
  }, []);

  // Filter/sort patients when search query changes
  useEffect(() => {
    if (!searchQuery.trim()) {
      setDisplayedPatients(allPatients);
      return;
    }
    const q = searchQuery.toLowerCase();
    const matched = [];
    const unmatched = [];
    for (const p of allPatients) {
      const name = (p.full_name || `${p.first_name} ${p.last_name}`).toLowerCase();
      const phone = (p.primary_phone || '').toLowerCase();
      const pid = (p.patient_id || '').toLowerCase();
      if (name.includes(q) || phone.includes(q) || pid.includes(q)) {
        matched.push(p);
      } else {
        unmatched.push(p);
      }
    }
    setDisplayedPatients([...matched, ...unmatched]);
    setCurrentPage(1);
  }, [searchQuery, allPatients]);

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

  const selectPatient = async (patient) => {
    setSelectedPatient(patient);
    setSearchQuery('');
    setLoadingHistory(true);
    try {
      const res = await fetch(`/api/ehr/patient/${patient.patient_id}/history`, { headers });
      if (res.ok) {
        setPatientHistory(await res.json());
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setLoadingHistory(false);
    }
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
    };
    return map[status] || 'bg-gray-100 text-gray-600';
  };

  const typeIcon = (type) => {
    if (type === 'consultation') return <Stethoscope className="h-4 w-4" />;
    if (type === 'prescription') return <Pill className="h-4 w-4" />;
    if (type === 'lab_order') return <TestTube className="h-4 w-4" />;
    return <FileText className="h-4 w-4" />;
  };

  const typeColor = (type) => {
    if (type === 'consultation') return 'border-l-blue-500 bg-blue-50/30';
    if (type === 'prescription') return 'border-l-green-500 bg-green-50/30';
    if (type === 'lab_order') return 'border-l-purple-500 bg-purple-50/30';
    return 'border-l-gray-500';
  };

  const typeLabel = (type) => {
    if (type === 'consultation') return 'Consultation';
    if (type === 'prescription') return 'Prescription';
    if (type === 'lab_order') return 'Lab Order';
    return type;
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

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {selectedPatient && (
            <Button variant="ghost" size="sm" onClick={() => { setSelectedPatient(null); setPatientHistory(null); }}>
              <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
          )}
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" /> Electronic Health Records
          </h1>
        </div>
      </div>

      {/* Patient Search + Full List */}
      {!selectedPatient && (
        <Card>
          <CardContent className="pt-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Search patient by name, phone, or patient ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>

            {loadingPatients ? (
              <div className="text-center py-12 text-gray-500 text-sm">Loading patients...</div>
            ) : (
              <>
                <div className="mt-3">
                  {displayedPatients.length === 0 ? (
                    <p className="text-center text-gray-400 py-12 text-sm">No patients found.</p>
                  ) : (
                    <>
                      <div className="text-xs text-gray-500 mb-2">
                        Showing {Math.min((currentPage - 1) * patientsPerPage + 1, displayedPatients.length)}–{Math.min(currentPage * patientsPerPage, displayedPatients.length)} of {displayedPatients.length} patients
                      </div>
                      <div className="border rounded-lg divide-y">
                        {displayedPatients.slice((currentPage - 1) * patientsPerPage, currentPage * patientsPerPage).map(p => {
                          const q = searchQuery.toLowerCase();
                          const isMatch = q && (
                            (p.full_name || `${p.first_name} ${p.last_name}`).toLowerCase().includes(q) ||
                            (p.primary_phone || '').includes(q) ||
                            (p.patient_id || '').toLowerCase().includes(q)
                          );
                          return (
                            <div
                              key={p.patient_id}
                              className={`flex items-center justify-between p-4 hover:bg-blue-50 cursor-pointer ${isMatch ? 'bg-yellow-50' : ''}`}
                              onClick={() => selectPatient(p)}
                            >
                              <div className="flex items-center gap-4">
                                <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                                  <User className="h-5 w-5 text-blue-600" />
                                </div>
                                <div>
                                  <p className="font-medium">{p.full_name || `${p.first_name} ${p.last_name}`}</p>
                                  <p className="text-sm text-gray-500">
                                    {p.gender}{p.age ? `, ${p.age} yrs` : ''} | {p.primary_phone}
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-3">
                                {p.blood_group && <Badge variant="secondary" className="text-xs">{p.blood_group}</Badge>}
                                <Badge variant="outline" className="text-xs">{p.patient_id.slice(0, 8)}...</Badge>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Pagination */}
                      {Math.ceil(displayedPatients.length / patientsPerPage) > 1 && (
                        <div className="flex items-center justify-between mt-4">
                          <Button
                            variant="outline" size="sm"
                            disabled={currentPage === 1}
                            onClick={() => setCurrentPage(prev => prev - 1)}
                          >
                            <ChevronLeft className="h-4 w-4 mr-1" /> Previous
                          </Button>
                          <div className="flex items-center gap-1">
                            {Array.from({ length: Math.ceil(displayedPatients.length / patientsPerPage) }, (_, i) => i + 1)
                              .filter(page => page === 1 || page === Math.ceil(displayedPatients.length / patientsPerPage) || Math.abs(page - currentPage) <= 2)
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
                              ))
                            }
                          </div>
                          <Button
                            variant="outline" size="sm"
                            disabled={currentPage >= Math.ceil(displayedPatients.length / patientsPerPage)}
                            onClick={() => setCurrentPage(prev => prev + 1)}
                          >
                            Next <ChevronRight className="h-4 w-4 ml-1" />
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loadingHistory && (
        <div className="text-center py-12 text-gray-500">
          <Activity className="h-8 w-8 mx-auto mb-2 animate-spin" />
          <p>Loading patient history...</p>
        </div>
      )}

      {/* Patient History View */}
      {patientHistory && !loadingHistory && (
        <>
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
                    <p className="text-xs text-gray-500">{patientHistory.patient.patient_id}</p>
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
              <div className="mt-4 pt-3 border-t grid grid-cols-3 gap-4">
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
              </div>
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="timeline"><Clock className="h-4 w-4 mr-1" /> Timeline</TabsTrigger>
              <TabsTrigger value="consultations"><Stethoscope className="h-4 w-4 mr-1" /> Consultations</TabsTrigger>
              <TabsTrigger value="prescriptions"><Pill className="h-4 w-4 mr-1" /> Prescriptions</TabsTrigger>
              <TabsTrigger value="lab"><TestTube className="h-4 w-4 mr-1" /> Lab</TabsTrigger>
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
                              <span className={`p-1 rounded ${item.type === 'consultation' ? 'bg-blue-100 text-blue-600' : item.type === 'prescription' ? 'bg-green-100 text-green-600' : 'bg-purple-100 text-purple-600'}`}>
                                {typeIcon(item.type)}
                              </span>
                              <Badge variant="outline" className="text-xs">{typeLabel(item.type)}</Badge>
                              <span className="text-xs text-gray-500 ml-auto">{formatDateTime(item.date)}</span>
                            </div>

                            {item.type === 'consultation' && renderConsultationCard(item.data, key)}
                            {item.type === 'prescription' && renderPrescriptionCard(item.data, key)}
                            {item.type === 'lab_order' && renderLabOrderCard(item.data, key)}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
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
          </Tabs>
        </>
      )}

    </div>
  );
};

export default EHRModule;
