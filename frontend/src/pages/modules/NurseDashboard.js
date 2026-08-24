import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { useToast } from '../../hooks/use-toast';
import {
  Search,
  User,
  Phone,
  Activity,
  RefreshCw,
  Bed,
  Plus,
  Eye,
} from 'lucide-react';
import axios from 'axios';
import VitalsForm from '../../components/vitals/VitalsForm';

const NurseDashboard = () => {
  const { toast } = useToast();
  const [patients, setPatients] = useState([]);
  const [filteredPatients, setFilteredPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const [activeTab, setActiveTab] = useState('patients');

  // Inpatient ward state
  const [inpatientEnabled, setInpatientEnabled] = useState(false);
  const [wardAdmissions, setWardAdmissions] = useState([]);
  const [showNurseVisitDialog, setShowNurseVisitDialog] = useState(false);
  const [nurseVisitAdmission, setNurseVisitAdmission] = useState(null);
  const [nurseVisitNotes, setNurseVisitNotes] = useState('');
  const [myPatientsOnly, setMyPatientsOnly] = useState(false);
  const [myPatients, setMyPatients] = useState([]);
  const [myPatientsShift, setMyPatientsShift] = useState('');

  useEffect(() => {
    fetchPatients();
    axios.get('/api/system/enabled-modules').then(res => {
      const mod = (res.data || []).find(m => m.module_name === 'inpatient');
      if (mod?.is_enabled) {
        setInpatientEnabled(true);
        axios.get('/api/inpatient/admissions', { params: { status: 'admitted' } })
          .then(r => setWardAdmissions(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
          .catch(() => {});
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!myPatientsOnly) return;
    const params = {};
    if (myPatientsShift) params.shift = myPatientsShift;
    axios.get('/api/inpatient/nurses/my-patients', { params })
      .then(r => setMyPatients(r.data || []))
      .catch(() => setMyPatients([]));
  }, [myPatientsOnly, myPatientsShift]);

  useEffect(() => {
    let filtered = patients;
    if (searchTerm) {
      filtered = filtered.filter(patient =>
        patient.first_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        patient.last_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        patient.primary_phone?.includes(searchTerm) ||
        patient.patient_id?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }
    setFilteredPatients(filtered);
  }, [patients, searchTerm]);

  const fetchPatients = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/patients/search', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          search_term: '',
          sort_by: 'name',
          sort_order: 'asc'
        })
      });

      if (response.ok) {
        const data = await response.json();
        setPatients(data.patients);
      }
    } catch (error) {
      console.error('Error fetching patients:', error);
    } finally {
      setLoading(false);
    }
  };

  const openVitalsForPatient = (patient) => {
    setSelectedPatient(patient);
    setShowVitalsDialog(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Nurse Dashboard</h1>
          <p className="text-gray-600">Patient care and vital signs monitoring</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchPatients} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className={`grid w-full ${inpatientEnabled ? 'grid-cols-2' : 'grid-cols-1'}`}>
          <TabsTrigger value="patients">Patient Care</TabsTrigger>
          {inpatientEnabled && <TabsTrigger value="ward">Inpatient Ward</TabsTrigger>}
        </TabsList>

        <TabsContent value="patients" className="space-y-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex gap-4 items-end">
                <div className="flex-1">
                  <Label>Search Patients</Label>
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    <Input
                      placeholder="Search by name, phone, or patient ID..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>Patients ({filteredPatients.length})</span>
                    {selectedPatient && (
                      <Badge className="bg-green-100 text-green-800">
                        Selected: {selectedPatient.first_name} {selectedPatient.last_name}
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                  ) : filteredPatients.length === 0 ? (
                    <div className="text-center py-8">
                      <User className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                      <p className="text-gray-500">No patients found</p>
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {filteredPatients.map((patient) => (
                        <Card
                          key={patient.id}
                          className={`cursor-pointer transition-all hover:shadow-md ${
                            selectedPatient?.id === patient.id ? 'border-blue-500 bg-blue-50' : ''
                          }`}
                          onClick={() => setSelectedPatient(patient)}
                        >
                          <CardContent className="pt-4">
                            <div className="flex justify-between items-start">
                              <div className="space-y-2">
                                <div className="flex items-center gap-2">
                                  <h4 className="font-semibold">
                                    {patient.first_name} {patient.last_name}
                                  </h4>
                                  {patient.gender && (
                                    <Badge variant="outline" className="text-xs">
                                      {patient.gender}
                                    </Badge>
                                  )}
                                  {patient.blood_group && (
                                    <Badge variant="outline" className="text-xs text-red-600">
                                      {patient.blood_group}
                                    </Badge>
                                  )}
                                  {patient.age && (
                                    <Badge variant="outline" className="text-xs">
                                      {patient.age}y
                                    </Badge>
                                  )}
                                </div>
                                <div className="text-sm text-gray-600">
                                  <p className="flex items-center gap-1">
                                    <Phone className="h-3 w-3" />
                                    {patient.primary_phone}
                                  </p>
                                  <p className="flex items-center gap-1">
                                    <User className="h-3 w-3" />
                                    ID: {patient.patient_id}
                                  </p>
                                </div>
                              </div>
                              <div className="flex gap-1">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openVitalsForPatient(patient);
                                  }}
                                >
                                  <Activity className="h-3 w-3" />
                                </Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              {selectedPatient && (
                <Card>
                  <CardHeader>
                    <CardTitle>Patient Actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <Button
                      onClick={() => setShowVitalsDialog(true)}
                      className="w-full flex items-center gap-2"
                    >
                      <Activity className="h-4 w-4" />
                      Record Vitals
                    </Button>
                    <Button
                      variant="outline"
                      className="w-full flex items-center gap-2"
                      disabled
                      title="Visit history is not available"
                    >
                      <Eye className="h-4 w-4" />
                      View History
                    </Button>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>Summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>Total Patients:</span>
                      <span className="font-medium">{patients.length}</span>
                    </div>
                    <p className="text-gray-500 text-xs pt-1">
                      Search a patient to record vitals. Outpatient appointments are no longer used.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {inpatientEnabled && (
          <TabsContent value="ward" className="space-y-4">
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded border">
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={myPatientsOnly} onChange={e => setMyPatientsOnly(e.target.checked)} />
                  <span className="text-sm font-medium">My Patients only</span>
                </label>
                {myPatientsOnly && (
                  <select className="text-sm border rounded px-2 py-1" value={myPatientsShift} onChange={e => setMyPatientsShift(e.target.value)}>
                    <option value="">Any shift (today)</option>
                    <option value="morning">Morning</option>
                    <option value="afternoon">Afternoon</option>
                    <option value="night">Night</option>
                  </select>
                )}
              </div>
              {myPatientsOnly && (
                <span className="text-xs text-gray-500">{myPatients.length} assigned</span>
              )}
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bed className="h-5 w-5" /> {myPatientsOnly ? 'My Assigned Patients' : 'Inpatient Ward'}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {myPatientsOnly ? (
                  myPatients.length === 0 ? (
                    <p className="text-gray-500 text-center py-4">No patients assigned to you{myPatientsShift ? ` for ${myPatientsShift} shift` : ''}.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 text-sm">Patient</th>
                            <th className="text-left py-2 text-sm">Room</th>
                            <th className="text-left py-2 text-sm">Shift</th>
                            <th className="text-left py-2 text-sm">Role</th>
                            <th className="text-left py-2 text-sm">Notes</th>
                            <th className="text-left py-2 text-sm">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {myPatients.map(mp => (
                            <tr key={`${mp.admission_id}-${mp.shift}`} className="border-b hover:bg-gray-50">
                              <td className="py-2">
                                <div className="font-medium text-sm">{mp.patient_name || 'N/A'}</div>
                                <div className="text-xs text-gray-500">{mp.admission_number}</div>
                              </td>
                              <td className="py-2 text-sm">{mp.room_number} <span className="text-xs text-gray-500">({mp.room_type})</span></td>
                              <td className="py-2 text-sm"><Badge variant="outline" className="text-xs">{mp.shift}</Badge></td>
                              <td className="py-2 text-sm">{mp.is_primary ? <Badge className="text-xs bg-blue-100 text-blue-800">Primary</Badge> : '—'}</td>
                              <td className="py-2 text-sm text-gray-600">{mp.assignment_notes || '—'}</td>
                              <td className="py-2">
                                <Button size="sm" variant="outline" onClick={() => { setNurseVisitAdmission({ id: mp.admission_id, patient_name: mp.patient_name, admission_number: mp.admission_number }); setNurseVisitNotes(''); setShowNurseVisitDialog(true); }}>
                                  <Plus className="h-3 w-3 mr-1" /> Record Visit
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                ) : wardAdmissions.length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No active admissions.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 text-sm">Patient</th>
                          <th className="text-left py-2 text-sm">Room</th>
                          <th className="text-left py-2 text-sm">Admitted</th>
                          <th className="text-left py-2 text-sm">Doctor</th>
                          <th className="text-left py-2 text-sm">Days</th>
                          <th className="text-left py-2 text-sm">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wardAdmissions.map(adm => (
                          <tr key={adm.id} className="border-b hover:bg-gray-50">
                            <td className="py-2">
                              <div className="font-medium text-sm">{adm.patient_name || 'N/A'}</div>
                              <div className="text-xs text-gray-500">{adm.admission_number}</div>
                            </td>
                            <td className="py-2 text-sm">{adm.room_number} {adm.bed_number ? `/ ${adm.bed_number}` : ''}</td>
                            <td className="py-2 text-sm">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : ''}</td>
                            <td className="py-2 text-sm">{adm.doctor_name || 'N/A'}</td>
                            <td className="py-2 text-sm">{adm.admission_date ? Math.max(1, Math.floor((Date.now() - new Date(adm.admission_date).getTime()) / 86400000)) : 0}</td>
                            <td className="py-2">
                              <Button size="sm" variant="outline" onClick={() => { setNurseVisitAdmission(adm); setNurseVisitNotes(''); setShowNurseVisitDialog(true); }}>
                                <Plus className="h-3 w-3 mr-1" /> Record Visit
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      <Dialog open={showNurseVisitDialog} onOpenChange={setShowNurseVisitDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Record Nurse Visit - {nurseVisitAdmission?.patient_name}</DialogTitle>
          </DialogHeader>
          <form onSubmit={async (e) => {
            e.preventDefault();
            try {
              const userData = JSON.parse(localStorage.getItem('user') || '{}');
              await axios.post(`/api/inpatient/admissions/${nurseVisitAdmission.id}/visits`, {
                visit_type: 'nurse_visit',
                visitor_id: userData.id,
                notes: nurseVisitNotes || null,
              });
              toast({ title: 'Success', description: 'Nurse visit recorded' });
              setShowNurseVisitDialog(false);
              axios.get('/api/inpatient/admissions', { params: { status: 'admitted' } })
                .then(r => setWardAdmissions(Array.isArray(r.data) ? r.data : (r.data?.items || []))).catch(() => {});
            } catch (err) {
              toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to record visit' });
            }
          }} className="space-y-4">
            <div>
              <Label>Nursing Notes</Label>
              <Textarea value={nurseVisitNotes} onChange={e => setNurseVisitNotes(e.target.value)} rows={4} placeholder="Patient observations, vitals summary, care notes..." />
            </div>
            <Button type="submit" className="w-full">Record Visit</Button>
          </form>
        </DialogContent>
      </Dialog>

      <VitalsForm
        isOpen={showVitalsDialog}
        onClose={() => setShowVitalsDialog(false)}
        selectedPatient={selectedPatient}
        userRole="nurse"
      />
    </div>
  );
};

export default NurseDashboard;
