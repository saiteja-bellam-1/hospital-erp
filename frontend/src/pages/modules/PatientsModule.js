import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { useToast } from '../../hooks/use-toast';
import {
  Users, UserPlus, Search, Phone, Calendar, Eye, Edit, RefreshCw, BedDouble
} from 'lucide-react';
import axios from 'axios';

const PatientsModule = () => {
  const { toast } = useToast();
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [inpatientEnabled, setInpatientEnabled] = useState(false);
  const [admissions, setAdmissions] = useState([]);
  const [loadingAdmissions, setLoadingAdmissions] = useState(false);

  const [patientForm, setPatientForm] = useState({
    first_name: '', last_name: '', date_of_birth: '', age: '', gender: '',
    primary_phone: '', email: '', blood_group: '', marital_status: '',
    abha_id: '', address_line1: '', address_line2: '', village: '',
    mandal: '', district: '', emergency_contact_name: '',
    emergency_contact_phone: '', emergency_contact_relation: '',
  });

  const resetForm = () => {
    setPatientForm({
      first_name: '', last_name: '', date_of_birth: '', gender: '',
      primary_phone: '', email: '', blood_group: '', marital_status: '',
      abha_id: '', address_line1: '', address_line2: '', village: '',
      mandal: '', district: '', emergency_contact_name: '',
      emergency_contact_phone: '', emergency_contact_relation: '',
    });
  };

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

  useEffect(() => {
    axios.get('/api/system/enabled-modules').then(res => {
      const mod = (res.data || []).find(m => m.module_name === 'inpatient');
      if (mod?.is_enabled) setInpatientEnabled(true);
    }).catch(() => {});
  }, []);

  const handleRegister = async () => {
    if (!patientForm.first_name || !patientForm.last_name || !patientForm.primary_phone) {
      toast({ variant: 'destructive', title: 'Error', description: 'First name, last name and phone are required' });
      return;
    }
    if (!patientForm.age) {
      toast({ variant: 'destructive', title: 'Error', description: 'Age is required (enter age or pick a date of birth)' });
      return;
    }
    setRegistering(true);
    try {
      await axios.post('/api/patients/', {
        ...patientForm,
        age: parseInt(patientForm.age),
        date_of_birth: patientForm.date_of_birth || null,
      });
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
                <div key={patient.patient_id} className="flex items-center justify-between py-3 hover:bg-gray-50 px-2 rounded">
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
                  <div className="flex items-center gap-2">
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

      {/* Register Patient Dialog */}
      <Dialog open={showRegisterDialog} onOpenChange={setShowRegisterDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register New Patient</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>First Name *</Label>
                <Input value={patientForm.first_name} onChange={(e) => setPatientForm({ ...patientForm, first_name: e.target.value })} />
              </div>
              <div>
                <Label>Last Name *</Label>
                <Input value={patientForm.last_name} onChange={(e) => setPatientForm({ ...patientForm, last_name: e.target.value })} />
              </div>
              <div>
                <Label>Phone *</Label>
                <Input value={patientForm.primary_phone} onChange={(e) => setPatientForm({ ...patientForm, primary_phone: e.target.value })} />
              </div>
              <div>
                <Label>Email</Label>
                <Input type="email" value={patientForm.email} onChange={(e) => setPatientForm({ ...patientForm, email: e.target.value })} />
              </div>
              <div>
                <Label>Date of Birth</Label>
                <Input
                  type="date"
                  value={patientForm.date_of_birth}
                  onChange={(e) => {
                    const dob = e.target.value;
                    const updates = { date_of_birth: dob };
                    if (dob) {
                      const today = new Date();
                      const birth = new Date(dob);
                      let calcAge = today.getFullYear() - birth.getFullYear();
                      if (today.getMonth() < birth.getMonth() || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) calcAge--;
                      updates.age = calcAge >= 0 ? String(calcAge) : '';
                    }
                    setPatientForm(prev => ({ ...prev, ...updates }));
                  }}
                />
              </div>
              <div>
                <Label>Age (years) <span className="text-red-500">*</span></Label>
                <Input
                  type="number"
                  min="0"
                  max="150"
                  placeholder="Enter age"
                  value={patientForm.age}
                  onChange={(e) => setPatientForm({ ...patientForm, age: e.target.value, date_of_birth: '' })}
                />
              </div>
              <div>
                <Label>Gender</Label>
                <Select value={patientForm.gender} onValueChange={(v) => setPatientForm({ ...patientForm, gender: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Male">Male</SelectItem>
                    <SelectItem value="Female">Female</SelectItem>
                    <SelectItem value="Other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Blood Group</Label>
                <Select value={patientForm.blood_group} onValueChange={(v) => setPatientForm({ ...patientForm, blood_group: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map(bg => (
                      <SelectItem key={bg} value={bg}>{bg}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Marital Status</Label>
                <Select value={patientForm.marital_status} onValueChange={(v) => setPatientForm({ ...patientForm, marital_status: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Single">Single</SelectItem>
                    <SelectItem value="Married">Married</SelectItem>
                    <SelectItem value="Divorced">Divorced</SelectItem>
                    <SelectItem value="Widowed">Widowed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>ABHA ID</Label>
                <Input value={patientForm.abha_id} onChange={(e) => setPatientForm({ ...patientForm, abha_id: e.target.value })} />
              </div>
            </div>

            {/* Address */}
            <div>
              <h4 className="font-medium text-sm text-gray-700 mb-2">Address</h4>
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label>Address Line 1</Label>
                  <Input value={patientForm.address_line1} onChange={(e) => setPatientForm({ ...patientForm, address_line1: e.target.value })} />
                </div>
                <div className="col-span-2">
                  <Label>Address Line 2</Label>
                  <Input value={patientForm.address_line2} onChange={(e) => setPatientForm({ ...patientForm, address_line2: e.target.value })} />
                </div>
                <div>
                  <Label>Village</Label>
                  <Input value={patientForm.village} onChange={(e) => setPatientForm({ ...patientForm, village: e.target.value })} />
                </div>
                <div>
                  <Label>Mandal</Label>
                  <Input value={patientForm.mandal} onChange={(e) => setPatientForm({ ...patientForm, mandal: e.target.value })} />
                </div>
                <div>
                  <Label>District</Label>
                  <Input value={patientForm.district} onChange={(e) => setPatientForm({ ...patientForm, district: e.target.value })} />
                </div>
              </div>
            </div>

            {/* Emergency Contact */}
            <div>
              <h4 className="font-medium text-sm text-gray-700 mb-2">Emergency Contact</h4>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label>Name</Label>
                  <Input value={patientForm.emergency_contact_name} onChange={(e) => setPatientForm({ ...patientForm, emergency_contact_name: e.target.value })} />
                </div>
                <div>
                  <Label>Phone</Label>
                  <Input value={patientForm.emergency_contact_phone} onChange={(e) => setPatientForm({ ...patientForm, emergency_contact_phone: e.target.value })} />
                </div>
                <div>
                  <Label>Relation</Label>
                  <Input value={patientForm.emergency_contact_relation} onChange={(e) => setPatientForm({ ...patientForm, emergency_contact_relation: e.target.value })} />
                </div>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowRegisterDialog(false)} className="flex-1">Cancel</Button>
              <Button onClick={handleRegister} disabled={registering} className="flex-1">
                {registering ? 'Registering...' : 'Register Patient'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
