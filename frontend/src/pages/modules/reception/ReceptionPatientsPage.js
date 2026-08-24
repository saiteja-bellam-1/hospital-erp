import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import {
  Search,
  User,
  Phone,
  MapPin,
  Filter,
  UserPlus,
  RefreshCw,
  Calendar,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import VitalsForm from '../../../components/vitals/VitalsForm';
import ReferralSelectWithCreate from '../../../components/ReferralSelectWithCreate';
import SteppedFormDialog from '../../../components/SteppedFormDialog';
import PatientRegisterFormFields, {
  EMPTY_PATIENT_FORM,
  PATIENT_FORM_STEPS,
  buildPatientPayload,
  patientStepCanProceed,
  validatePatientForm,
} from '../../../components/PatientRegisterFormFields';
import { useToast } from '../../../hooks/use-toast';
import { applyDobToForm, formatPatientAge, hasValidAge, parseAgeFields } from '../../../utils/patientAge';

const ReceptionPatientsPage = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [patients, setPatients] = useState([]);
  const [searchMetadata, setSearchMetadata] = useState({ total_count: 0, page: 1, per_page: 10, total_pages: 0 });
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  
  // Dialogs
  const [showPatientDialog, setShowPatientDialog] = useState(false);
  const [showEditPatientDialog, setShowEditPatientDialog] = useState(false);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);

  // Edit patient form
  const [editPatientForm, setEditPatientForm] = useState({
    first_name: '', last_name: '', date_of_birth: '', age: '', age_months: '', gender: '',
    blood_group: '', marital_status: '', abha_id: '', gstin: '', email: '', referred_by: '',
    emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
    address_line1: '', address_line2: '', village: '', mandal: '', district: ''
  });

  // Filter states
  const [filterGender, setFilterGender] = useState('all');
  const [filterBloodGroup, setFilterBloodGroup] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const patientsPerPage = 10;
  const filterKey = `${searchTerm}|${filterGender}|${filterBloodGroup}`;
  const prevFilterKey = useRef(filterKey);

  // Forms
  const [patientForm, setPatientForm] = useState(EMPTY_PATIENT_FORM);
  const [registerStep, setRegisterStep] = useState(0);
  const registerSteps = useMemo(
    () => PATIENT_FORM_STEPS.map((s, i) => ({ ...s, completed: i < registerStep })),
    [registerStep],
  );

  // Fetch patients from API with server-side pagination
  useEffect(() => {
    const filtersChanged = prevFilterKey.current !== filterKey;
    prevFilterKey.current = filterKey;

    if (filtersChanged && currentPage !== 1) {
      setCurrentPage(1);
      return;
    }

    const pageToFetch = filtersChanged ? 1 : currentPage;
    const timer = setTimeout(() => {
      fetchPatients(pageToFetch);
    }, searchTerm ? 300 : 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, filterKey, searchTerm]);

  // Universal search jump: open patient history when available
  useEffect(() => {
    const incoming = location.state?.searchPatient;
    if (!incoming) return;
    const term =
      incoming.primary_phone ||
      incoming.mrn ||
      [incoming.first_name, incoming.last_name].filter(Boolean).join(' ').trim() ||
      '';
    if (term) setSearchTerm(term);
    setSelectedPatient(incoming);
    setShowHistoryDialog(true);
    navigate(location.pathname, { replace: true, state: {} });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const openPatientChart = (patient) => {
    setSelectedPatient(patient);
    setShowHistoryDialog(true);
  };

  const fetchPatients = async (page = currentPage) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/patients/search?page=${page}&per_page=${patientsPerPage}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            search_term: searchTerm || '',
            sort_by: 'name',
            sort_order: 'asc',
            gender: filterGender !== 'all' ? filterGender : null,
            blood_group: filterBloodGroup !== 'all' ? filterBloodGroup : null,
          })
        }
      );
      if (response.ok) {
        const data = await response.json();
        setPatients(data.patients || []);
        setSearchMetadata(data.metadata || { total_count: 0, page: 1, per_page: patientsPerPage, total_pages: 0 });
      }
    } catch (error) {
      console.error('Error fetching patients:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterNext = () => {
    const err = validatePatientForm(patientForm);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      return;
    }
    setRegisterStep((s) => Math.min(s + 1, PATIENT_FORM_STEPS.length - 1));
  };

  const createPatient = async () => {
    const err = validatePatientForm(patientForm);
    if (err) {
      toast({ variant: 'destructive', title: 'Missing fields', description: err });
      setRegisterStep(0);
      return;
    }
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/patients/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(buildPatientPayload(patientForm)),
      });
      if (response.ok) {
        const newPatient = await response.json();
        setSelectedPatient(newPatient);
        setShowPatientDialog(false);
        setCurrentPage(1);
        fetchPatients(1);
        setPatientForm(EMPTY_PATIENT_FORM);
        setRegisterStep(0);
        toast({ title: 'Success', description: 'Patient registered successfully!' });
      } else {
        const errorData = await response.json();
        console.error('Patient creation failed:', errorData);
        const errMsg = typeof errorData.detail === 'string'
          ? errorData.detail
          : Array.isArray(errorData.detail)
            ? errorData.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ')
            : 'Registration failed';
        toast({ title: 'Registration Failed', description: errMsg, variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error creating patient:', error);
      toast({ title: 'Error', description: 'Error registering patient', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const clearFilters = () => {
    setSearchTerm('');
    setFilterGender('all');
    setFilterBloodGroup('all');
    setCurrentPage(1);
  };

  const totalPatients = searchMetadata.total_count || 0;
  const totalPages = searchMetadata.total_pages || 0;
  const pageStart = totalPatients === 0 ? 0 : (currentPage - 1) * patientsPerPage + 1;
  const pageEnd = Math.min(currentPage * patientsPerPage, totalPatients);

  const openEditPatient = (patient) => {
    setSelectedPatient(patient);
    setEditPatientForm({
      first_name: patient.first_name || '',
      last_name: patient.last_name || '',
      date_of_birth: patient.date_of_birth || '',
      age: patient.age != null ? String(patient.age) : '',
      age_months: patient.age_months != null ? String(patient.age_months) : '',
      gender: patient.gender || '',
      blood_group: patient.blood_group || '',
      marital_status: patient.marital_status || '',
      abha_id: patient.abha_id || '',
      gstin: patient.gstin || '',
      email: patient.email || '',
      referred_by: patient.referred_by || '',
      emergency_contact_name: patient.emergency_contact_name || '',
      emergency_contact_phone: patient.emergency_contact_phone || '',
      emergency_contact_relation: patient.emergency_contact_relation || '',
      address_line1: patient.address_line1 || '',
      address_line2: patient.address_line2 || '',
      village: patient.village || '',
      mandal: patient.mandal || '',
      district: patient.district || '',
    });
    setShowEditPatientDialog(true);
  };

  const handleUpdatePatient = async () => {
    if (!selectedPatient) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      // Only send fields that have values
      const updateData = {};
      Object.entries(editPatientForm).forEach(([key, value]) => {
        if (value !== '' && value !== null && value !== undefined) {
          updateData[key] = ['age', 'age_months'].includes(key) ? parseInt(value, 10) : value;
        }
      });

      const response = await fetch(`/api/patients/${selectedPatient.patient_id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updateData)
      });
      if (response.ok) {
        toast({ title: 'Success', description: 'Patient updated successfully!' });
        setShowEditPatientDialog(false);
        fetchPatients();
      } else {
        const err = await response.json();
        toast({ title: 'Update Failed', description: err.detail || 'Failed to update patient', variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error updating patient:', error);
      toast({ title: 'Error', description: 'Error updating patient', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Patient Management</h1>
          <p className="text-gray-600">Register and manage patient information</p>
        </div>
        <div className="flex space-x-3">
          <Button onClick={fetchPatients} variant="outline" className="flex items-center space-x-2">
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </Button>
          <Button className="flex items-center space-x-2" onClick={() => { setRegisterStep(0); setShowPatientDialog(true); }}>
            <UserPlus className="h-4 w-4" />
            <span>Register Patient</span>
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="Search by name, phone, or patient ID..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
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
              {(searchTerm || (filterGender && filterGender !== 'all') || (filterBloodGroup && filterBloodGroup !== 'all')) && (
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

      {/* Patients List */}
      <Card>
        <CardHeader>
          <CardTitle>Patients ({totalPatients})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin mr-2" />
              <span>Loading patients...</span>
            </div>
          ) : patients.length === 0 ? (
            <div className="text-center py-8">
              <User className="h-12 w-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-500 mb-3">
                {searchTerm || (filterGender && filterGender !== 'all') || (filterBloodGroup && filterBloodGroup !== 'all') 
                  ? 'No patients found matching your criteria'
                  : 'No patients registered yet'
                }
              </p>
              <Button onClick={() => { setRegisterStep(0); setShowPatientDialog(true); }}>
                <UserPlus className="h-4 w-4 mr-2" />
                Register First Patient
              </Button>
            </div>
          ) : (
            <>
              <div className="text-xs text-gray-500 mb-2">
                Showing {pageStart}–{pageEnd} of {totalPatients} patients
              </div>
              <div className="space-y-3">
                {patients.map((patient) => (
                  <div key={patient.patient_id} className="border rounded-lg p-4 hover:bg-gray-50">
                    <div className="flex justify-between items-start">
                      <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <div className="flex items-center space-x-2">
                            <User className="h-4 w-4 text-gray-500" />
                            <span className="font-semibold">
                              {patient.first_name} {patient.last_name}
                            </span>
                          </div>
                          <p className="text-sm text-gray-600 mt-1">ID: {patient.patient_id?.slice(0, 8)}...</p>
                          {(patient.date_of_birth || patient.age != null || patient.age_months != null) && (
                            <p className="text-sm text-gray-600">
                              Age: {formatPatientAge(patient)}
                            </p>
                          )}
                        </div>

                        <div>
                          <div className="flex items-center space-x-2 mb-1">
                            <Phone className="h-4 w-4 text-gray-500" />
                            <span className="text-sm">{patient.primary_phone}</span>
                          </div>
                          <div className="flex space-x-2">
                            {patient.gender && (
                              <Badge variant="outline">{patient.gender}</Badge>
                            )}
                            {patient.blood_group && (
                              <Badge variant="secondary">{patient.blood_group}</Badge>
                            )}
                          </div>
                        </div>

                        <div>
                          {patient.address && (
                            <div className="flex items-start space-x-2">
                              <MapPin className="h-4 w-4 text-gray-500 mt-0.5" />
                              <span className="text-sm">{patient.address}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex space-x-2">
                        <Button size="sm" variant="outline" onClick={() => openPatientChart(patient)}>
                          View Chart
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEditPatient(patient)}>
                          Edit
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <Button
                    variant="outline" size="sm"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(prev => prev - 1)}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" /> Previous
                  </Button>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                      .filter(page => page === 1 || page === totalPages || Math.abs(page - currentPage) <= 2)
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
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage(prev => prev + 1)}
                  >
                    Next <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <SteppedFormDialog
        open={showPatientDialog}
        onOpenChange={(open) => {
          setShowPatientDialog(open);
          if (!open) {
            setPatientForm(EMPTY_PATIENT_FORM);
            setRegisterStep(0);
          } else {
            setRegisterStep(0);
          }
        }}
        title="Register New Patient"
        steps={registerSteps}
        activeStep={registerStep}
        onStepChange={setRegisterStep}
        onNext={handleRegisterNext}
        onSave={createPatient}
        saving={loading}
        canProceed={registerStep !== 0 || patientStepCanProceed(patientForm, 0)}
        saveLabel="Register Patient"
      >
        <PatientRegisterFormFields
          form={patientForm}
          onChange={setPatientForm}
          activeStep={registerStep}
        />
      </SteppedFormDialog>

      {/* Edit Patient Dialog */}
      <Dialog open={showEditPatientDialog} onOpenChange={setShowEditPatientDialog}>
        <DialogContent className="max-w-6xl w-[96vw] max-h-[90vh] flex flex-col overflow-hidden gap-0 p-0">
          <div className="shrink-0 border-b px-6 pt-5 pb-3">
            <DialogHeader className="space-y-0">
              <DialogTitle>Edit Patient - {selectedPatient?.first_name} {selectedPatient?.last_name}</DialogTitle>
            </DialogHeader>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-3 gap-y-2">
            <div>
              <Label>First Name *</Label>
              <Input
                value={editPatientForm.first_name}
                onChange={(e) => setEditPatientForm({...editPatientForm, first_name: e.target.value})}
              />
            </div>
            <div>
              <Label>Last Name *</Label>
              <Input
                value={editPatientForm.last_name}
                onChange={(e) => setEditPatientForm({...editPatientForm, last_name: e.target.value})}
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
                onChange={(e) => setEditPatientForm({...editPatientForm, age: e.target.value, date_of_birth: ''})}
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
                onChange={(e) => setEditPatientForm({...editPatientForm, age_months: e.target.value, date_of_birth: ''})}
              />
            </div>
            <div>
              <Label>Gender</Label>
              <Select value={editPatientForm.gender || 'none'} onValueChange={(value) => setEditPatientForm({...editPatientForm, gender: value === 'none' ? '' : value})}>
                <SelectTrigger>
                  <SelectValue placeholder="Select Gender" />
                </SelectTrigger>
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
              <Select value={editPatientForm.blood_group || 'none'} onValueChange={(value) => setEditPatientForm({...editPatientForm, blood_group: value === 'none' ? '' : value})}>
                <SelectTrigger>
                  <SelectValue placeholder="Select Blood Group" />
                </SelectTrigger>
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
              <Select value={editPatientForm.marital_status || 'none'} onValueChange={(value) => setEditPatientForm({...editPatientForm, marital_status: value === 'none' ? '' : value})}>
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
              <Input value={editPatientForm.abha_id} onChange={(e) => setEditPatientForm({...editPatientForm, abha_id: e.target.value})} placeholder="14-digit ABHA number" />
            </div>
            <div>
              <Label>GSTIN (optional)</Label>
              <Input value={editPatientForm.gstin || ''} onChange={(e) => setEditPatientForm({...editPatientForm, gstin: e.target.value.toUpperCase()})} placeholder="Customer GSTIN" maxLength={15} />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={editPatientForm.email} onChange={(e) => setEditPatientForm({...editPatientForm, email: e.target.value})} placeholder="patient@email.com" />
            </div>
            <ReferralSelectWithCreate
              value={editPatientForm.referred_by || ''}
              onValueChange={(name) => setEditPatientForm({ ...editPatientForm, referred_by: name })}
            />

            {/* Emergency Contact Section */}
            <div className="col-span-full border-t pt-2 mt-1">
              <Label className="text-sm font-semibold text-gray-700">Emergency Contact</Label>
            </div>
            <div>
              <Label>Contact Name</Label>
              <Input value={editPatientForm.emergency_contact_name} onChange={(e) => setEditPatientForm({...editPatientForm, emergency_contact_name: e.target.value})} placeholder="Emergency contact name" />
            </div>
            <div>
              <Label>Contact Phone</Label>
              <Input value={editPatientForm.emergency_contact_phone} onChange={(e) => setEditPatientForm({...editPatientForm, emergency_contact_phone: e.target.value})} placeholder="Phone number" />
            </div>
            <div>
              <Label>Relation</Label>
              <Select value={editPatientForm.emergency_contact_relation || 'none'} onValueChange={(value) => setEditPatientForm({...editPatientForm, emergency_contact_relation: value === 'none' ? '' : value})}>
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

            {/* Address Section */}
            <div className="col-span-full border-t pt-2 mt-1">
              <Label className="text-sm font-semibold text-gray-700">Address</Label>
            </div>
            <div className="md:col-span-2 lg:col-span-3 xl:col-span-2">
              <Label>Address Line 1</Label>
              <Input value={editPatientForm.address_line1} onChange={(e) => setEditPatientForm({...editPatientForm, address_line1: e.target.value})} placeholder="House/Flat No, Street" />
            </div>
            <div className="md:col-span-2 lg:col-span-3 xl:col-span-2">
              <Label>Address Line 2</Label>
              <Input value={editPatientForm.address_line2} onChange={(e) => setEditPatientForm({...editPatientForm, address_line2: e.target.value})} placeholder="Area, Landmark" />
            </div>
            <div>
              <Label>Village / Town</Label>
              <Input value={editPatientForm.village} onChange={(e) => setEditPatientForm({...editPatientForm, village: e.target.value})} />
            </div>
            <div>
              <Label>Mandal / Taluka</Label>
              <Input value={editPatientForm.mandal} onChange={(e) => setEditPatientForm({...editPatientForm, mandal: e.target.value})} />
            </div>
            <div>
              <Label>District</Label>
              <Input value={editPatientForm.district} onChange={(e) => setEditPatientForm({...editPatientForm, district: e.target.value})} />
            </div>
          </div>
          </div>
          <div className="shrink-0 border-t px-6 py-3 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <Button variant="outline" onClick={() => setShowEditPatientDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdatePatient}
              disabled={loading || !editPatientForm.first_name || !editPatientForm.last_name || !editPatientForm.age}
            >
              {loading ? 'Updating...' : 'Update Patient'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Vitals Dialog — VitalsForm renders its own Dialog shell */}
      <VitalsForm
        isOpen={showVitalsDialog}
        onClose={() => setShowVitalsDialog(false)}
        selectedPatient={selectedPatient}
        userRole="receptionist"
        onSave={() => {
          setShowVitalsDialog(false);
          toast({ title: 'Success', description: 'Vitals recorded successfully!' });
        }}
      />

      {/* Patient chart dialog (appointment history removed with OPD) */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              Patient — {selectedPatient?.first_name} {selectedPatient?.last_name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {selectedPatient && (
              <div className="text-sm text-gray-600 space-y-1 border rounded-lg p-3">
                <p><span className="font-medium text-gray-800">ID:</span> {selectedPatient.patient_id}</p>
                {selectedPatient.primary_phone && (
                  <p><span className="font-medium text-gray-800">Phone:</span> {selectedPatient.primary_phone}</p>
                )}
                {(selectedPatient.age != null || selectedPatient.gender) && (
                  <p>
                    {selectedPatient.age != null && <span>{selectedPatient.age}y</span>}
                    {selectedPatient.age != null && selectedPatient.gender && ' · '}
                    {selectedPatient.gender}
                  </p>
                )}
              </div>
            )}
            <div className="text-center py-6">
              <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-500">No outpatient visit history available</p>
            </div>
            <div className="flex justify-end pt-2">
              <Button variant="outline" onClick={() => setShowHistoryDialog(false)}>Close</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
};

export default ReceptionPatientsPage;