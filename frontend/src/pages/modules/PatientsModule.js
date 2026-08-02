import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { useToast } from '../../hooks/use-toast';
import {
  Users, UserPlus, Search, Phone, Calendar, Eye, RefreshCw, BedDouble
} from 'lucide-react';
import axios from 'axios';
import { formatPatientAge } from '../../utils/patientAge';
import SteppedFormDialog from '../../components/SteppedFormDialog';
import PatientRegisterFormFields, {
  EMPTY_PATIENT_FORM,
  PATIENT_FORM_STEPS,
  buildPatientPayload,
  patientStepCanProceed,
  validatePatientForm,
} from '../../components/PatientRegisterFormFields';

const PatientsModule = () => {
  const { toast } = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [registerStep, setRegisterStep] = useState(0);
  const [inpatientEnabled, setInpatientEnabled] = useState(false);
  const [ehrEnabled, setEhrEnabled] = useState(false);
  const [admissions, setAdmissions] = useState([]);
  const [loadingAdmissions, setLoadingAdmissions] = useState(false);

  const [patientForm, setPatientForm] = useState(EMPTY_PATIENT_FORM);

  const resetForm = () => {
    setPatientForm(EMPTY_PATIENT_FORM);
    setRegisterStep(0);
  };

  const registerSteps = useMemo(
    () => PATIENT_FORM_STEPS.map((s, i) => ({ ...s, completed: i < registerStep })),
    [registerStep],
  );

  const fetchPatients = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.post('/api/patients/search', {
        search_term: searchQuery, sort_by: 'name', sort_order: 'asc'
      });
      setPatients(response.data.patients || []);
    } catch (error) {
      console.error('Failed to fetch patients:', error);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    fetchPatients();
  }, [fetchPatients]);

  // Universal search jump: open full patient chart in EHR when available
  useEffect(() => {
    const incoming = location.state?.searchPatient;
    if (!incoming) return;
    const uuid = incoming.patient_id;
    if (uuid) {
      navigate(`/dashboard/ehr/patient/${encodeURIComponent(uuid)}`, { replace: true });
      return;
    }
    const term =
      incoming.primary_phone ||
      incoming.mrn ||
      [incoming.first_name, incoming.last_name].filter(Boolean).join(' ').trim() ||
      '';
    if (term) setSearchQuery(term);
    setSelectedPatient(incoming);
    setShowDetailDialog(true);
    navigate(location.pathname, { replace: true, state: {} });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  useEffect(() => {
    axios.get('/api/system/enabled-modules').then(res => {
      const mod = (res.data || []).find(m => m.module_name === 'inpatient');
      if (mod?.is_enabled) setInpatientEnabled(true);
      const ehr = (res.data || []).find(m => m.module_name === 'ehr');
      if (ehr?.is_enabled) setEhrEnabled(true);
    }).catch(() => {});
  }, []);

  const handleRegisterNext = () => {
    const err = validatePatientForm(patientForm);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      return;
    }
    setRegisterStep((s) => Math.min(s + 1, PATIENT_FORM_STEPS.length - 1));
  };

  const handleRegister = async () => {
    const err = validatePatientForm(patientForm);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      setRegisterStep(0);
      return;
    }
    setRegistering(true);
    try {
      await axios.post('/api/patients/', buildPatientPayload(patientForm));
      toast({ title: 'Success', description: 'Patient registered successfully' });
      setShowRegisterDialog(false);
      resetForm();
      fetchPatients();
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: error.response?.data?.detail || 'Failed to register patient' });
    } finally {
      setRegistering(false);
    }
  };

  const viewPatientDetail = async (patientUuid) => {
    if (ehrEnabled && patientUuid) {
      navigate(`/dashboard/ehr/patient/${encodeURIComponent(patientUuid)}`);
      return;
    }
    try {
      const response = await axios.get(`/api/patients/${patientUuid}`);
      setSelectedPatient(response.data);
      setShowDetailDialog(true);
      setAdmissions([]);
      if (inpatientEnabled && response.data.id) {
        setLoadingAdmissions(true);
        try {
          const admRes = await axios.get(`/api/inpatient/admissions/patient/${response.data.id}`);
          setAdmissions(admRes.data || []);
        } catch { }
        setLoadingAdmissions(false);
      }
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load patient details' });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-900">Patient Management</h1>
        <Button onClick={() => { resetForm(); setShowRegisterDialog(true); }}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add New Patient
        </Button>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Search by name, phone, or patient ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button variant="outline" onClick={fetchPatients}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Patients list */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Patients ({patients.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-center text-gray-500 py-8">Loading patients...</p>
          ) : patients.length === 0 ? (
            <p className="text-center text-gray-500 py-8">No patients found</p>
          ) : (
            <div className="divide-y">
              {patients.map((patient) => (
                <div
                  key={patient.patient_id}
                  className="flex items-center justify-between py-3 hover:bg-gray-50 px-2 rounded cursor-pointer"
                  onClick={() => viewPatientDetail(patient.patient_id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {patient.mrn && (
                        <span className="font-mono text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                          {patient.mrn}
                        </span>
                      )}
                      <p className="font-medium text-gray-900">
                        {patient.first_name} {patient.last_name}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-500 mt-0.5">
                      <span className="flex items-center gap-1">
                        <Phone className="h-3 w-3" />
                        {patient.primary_phone}
                      </span>
                      {patient.gender && <Badge variant="outline" className="text-xs">{patient.gender}</Badge>}
                      {patient.blood_group && <Badge variant="secondary" className="text-xs">{patient.blood_group}</Badge>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" onClick={() => viewPatientDetail(patient.patient_id)}>
                      <Eye className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <SteppedFormDialog
        open={showRegisterDialog}
        onOpenChange={(open) => {
          setShowRegisterDialog(open);
          if (!open) resetForm();
        }}
        title="Register New Patient"
        steps={registerSteps}
        activeStep={registerStep}
        onStepChange={setRegisterStep}
        onNext={handleRegisterNext}
        onSave={handleRegister}
        saving={registering}
        canProceed={registerStep !== 0 || patientStepCanProceed(patientForm, 0)}
        saveLabel="Register Patient"
      >
        <PatientRegisterFormFields
          form={patientForm}
          onChange={setPatientForm}
          activeStep={registerStep}
        />
      </SteppedFormDialog>

      {/* Patient Detail Dialog */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className={inpatientEnabled ? "max-w-3xl max-h-[85vh] overflow-y-auto" : "max-w-lg"}>
          <DialogHeader>
            <DialogTitle>Patient Details</DialogTitle>
          </DialogHeader>
          {selectedPatient && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-500">Name:</span> <span className="font-medium">{selectedPatient.first_name} {selectedPatient.last_name}</span></div>
                <div><span className="text-gray-500">Phone:</span> <span className="font-medium">{selectedPatient.primary_phone}</span></div>
                <div><span className="text-gray-500">Gender:</span> <span className="font-medium">{selectedPatient.gender || '-'}</span></div>
                <div><span className="text-gray-500">DOB:</span> <span className="font-medium">{selectedPatient.date_of_birth || '-'}</span></div>
                <div><span className="text-gray-500">Blood Group:</span> <span className="font-medium">{selectedPatient.blood_group || '-'}</span></div>
                <div><span className="text-gray-500">MRN:</span> <span className="font-mono text-xs">{selectedPatient.mrn || '-'}</span></div>
                {selectedPatient.email && <div><span className="text-gray-500">Email:</span> <span className="font-medium">{selectedPatient.email}</span></div>}
                {selectedPatient.abha_id && <div><span className="text-gray-500">ABHA ID:</span> <span className="font-medium">{selectedPatient.abha_id}</span></div>}
              </div>
              {(selectedPatient.address_line1 || selectedPatient.village || selectedPatient.district) && (
                <div className="text-sm">
                  <span className="text-gray-500">Address:</span>
                  <p className="font-medium">
                    {[selectedPatient.address_line1, selectedPatient.address_line2, selectedPatient.village, selectedPatient.mandal, selectedPatient.district].filter(Boolean).join(', ')}
                  </p>
                </div>
              )}

              {/* Admission History */}
              {inpatientEnabled && (
                <div className="border-t pt-3 mt-3">
                  <h4 className="font-medium text-sm text-gray-700 mb-2 flex items-center gap-2">
                    <BedDouble className="h-4 w-4" />
                    Admission History
                  </h4>
                  {loadingAdmissions ? (
                    <p className="text-sm text-gray-500 py-2">Loading admissions...</p>
                  ) : admissions.length === 0 ? (
                    <p className="text-sm text-gray-500 py-2">No admission records found</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-gray-500">
                            <th className="py-1.5 pr-2">Admission No</th>
                            <th className="py-1.5 pr-2">Admission Date</th>
                            <th className="py-1.5 pr-2">Room</th>
                            <th className="py-1.5 pr-2">Doctor</th>
                            <th className="py-1.5 pr-2">Stay Days</th>
                            <th className="py-1.5 pr-2">Status</th>
                            <th className="py-1.5">Discharge Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {admissions.map((adm) => (
                            <tr key={adm.id} className="border-b last:border-0 hover:bg-gray-50">
                              <td className="py-1.5 pr-2 font-mono text-xs">{adm.admission_number}</td>
                              <td className="py-1.5 pr-2">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : '-'}</td>
                              <td className="py-1.5 pr-2">{adm.room_number || '-'}</td>
                              <td className="py-1.5 pr-2">{adm.doctor_name || '-'}</td>
                              <td className="py-1.5 pr-2">{adm.stay_days != null ? adm.stay_days : '-'}</td>
                              <td className="py-1.5 pr-2">
                                <Badge variant={adm.status === 'admitted' ? 'default' : 'secondary'}
                                  className={adm.status === 'admitted' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'}>
                                  {adm.status === 'admitted' ? 'Active' : 'Discharged'}
                                </Badge>
                              </td>
                              <td className="py-1.5">{adm.discharge_date ? new Date(adm.discharge_date).toLocaleDateString() : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              <Button variant="outline" onClick={() => setShowDetailDialog(false)} className="w-full mt-2">Close</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PatientsModule;
