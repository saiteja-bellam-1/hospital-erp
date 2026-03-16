import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../../components/ui/dialog';
import {
  Search,
  User,
  Phone,
  MapPin,
  Filter,
  UserPlus,
  RefreshCw,
  Activity,
  Pill,
  Eye,
  Pencil,
  History,
  Calendar,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import VitalsForm from '../../../components/vitals/VitalsForm';
import { useToast } from '../../../hooks/use-toast';

const ReceptionPatientsPage = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [filteredPatients, setFilteredPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  
  // Dialogs
  const [showPatientDialog, setShowPatientDialog] = useState(false);
  const [showEditPatientDialog, setShowEditPatientDialog] = useState(false);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const [showPrescriptionsDialog, setShowPrescriptionsDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [appointmentHistory, setAppointmentHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Edit patient form
  const [editPatientForm, setEditPatientForm] = useState({
    first_name: '', last_name: '', date_of_birth: '', age: '', gender: '',
    blood_group: '', marital_status: '', abha_id: '', email: '',
    emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
    address_line1: '', address_line2: '', village: '', mandal: '', district: ''
  });

  // Prescription state
  const [prescriptions, setPrescriptions] = useState([]);
  const [prescriptionsLoading, setPrescriptionsLoading] = useState(false);

  // Filter states
  const [filterGender, setFilterGender] = useState('all');
  const [filterBloodGroup, setFilterBloodGroup] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const patientsPerPage = 10;

  // Forms
  const [patientForm, setPatientForm] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
    age: '',
    gender: '',
    blood_group: '',
    marital_status: '',
    abha_id: '',
    email: '',
    primary_phone: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
    emergency_contact_relation: '',
    address_line1: '',
    address_line2: '',
    village: '',
    mandal: '',
    district: '',
    referred_by: '',
  });

  // Load initial data
  useEffect(() => {
    fetchPatients();
  }, []);

  // Filter and sort patients: matches come first, rest follow
  useEffect(() => {
    let filtered = patients;

    // Gender filter
    if (filterGender && filterGender !== 'all') {
      filtered = filtered.filter(patient => patient.gender === filterGender);
    }

    // Blood group filter
    if (filterBloodGroup && filterBloodGroup !== 'all') {
      filtered = filtered.filter(patient => patient.blood_group === filterBloodGroup);
    }

    // Search: bring matching patients to top instead of hiding others
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const matched = [];
      const rest = [];
      for (const patient of filtered) {
        const isMatch =
          patient.first_name?.toLowerCase().includes(q) ||
          patient.last_name?.toLowerCase().includes(q) ||
          patient.primary_phone?.includes(searchTerm) ||
          patient.patient_id?.toLowerCase().includes(q);
        if (isMatch) {
          matched.push({ ...patient, _isMatch: true });
        } else {
          rest.push({ ...patient, _isMatch: false });
        }
      }
      setFilteredPatients([...matched, ...rest]);
    } else {
      setFilteredPatients(filtered.map(p => ({ ...p, _isMatch: false })));
    }
    setCurrentPage(1);
  }, [patients, searchTerm, filterGender, filterBloodGroup]);

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

  const searchPatientByPhone = async (phone) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/patients/phone/${phone}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const patient = await response.json();
        setSelectedPatient(patient);
        return patient;
      }
    } catch (error) {
      console.error('Error searching patient:', error);
    }
    return null;
  };

  const createPatient = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/patients/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ...patientForm,
          age: patientForm.age ? parseInt(patientForm.age) : null,
          date_of_birth: patientForm.date_of_birth || null,
          email: patientForm.email || null
        })
      });
      if (response.ok) {
        const newPatient = await response.json();
        setPatients([newPatient, ...patients]);
        setSelectedPatient(newPatient);
        setShowPatientDialog(false);
        setPatientForm({
          first_name: '',
          last_name: '',
          date_of_birth: '',
          age: '',
          gender: '',
          blood_group: '',
          marital_status: '',
          abha_id: '',
          email: '',
          primary_phone: '',
          emergency_contact_name: '',
          emergency_contact_phone: '',
          emergency_contact_relation: '',
          address_line1: '',
          address_line2: '',
          village: '',
          mandal: '',
          district: '',
        });
        toast({ title: 'Success', description: 'Patient registered successfully!' });
      } else {
        const errorData = await response.json();
        console.error('Patient creation failed:', errorData);
        toast({ title: 'Registration Failed', description: errorData.detail || 'Unknown error', variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error creating patient:', error);
      toast({ title: 'Error', description: 'Error registering patient', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const fetchPrescriptions = async (patientId) => {
    setPrescriptionsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/prescriptions-simple/?patient_id=${patientId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      if (response.ok) {
        const data = await response.json();
        setPrescriptions(Array.isArray(data) ? data : []);
      } else {
        console.error('Failed to fetch prescriptions:', response.status);
        setPrescriptions([]);
      }
    } catch (error) {
      console.error('Error fetching prescriptions:', error);
      setPrescriptions([]);
    } finally {
      setPrescriptionsLoading(false);
    }
  };

  const printPrescription = async (prescriptionId, includeHeader = true) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/prescriptions-simple/${prescriptionId}/download?include_header=${includeHeader}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        // Create iframe for printing
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        iframe.src = url;
        
        iframe.onload = () => {
          iframe.contentWindow.print();
          setTimeout(() => {
            document.body.removeChild(iframe);
            window.URL.revokeObjectURL(url);
          }, 1000);
        };
      } else {
        toast({ title: 'Print Failed', description: 'Failed to print prescription', variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error printing prescription:', error);
      toast({ title: 'Error', description: 'Error printing prescription', variant: 'destructive' });
    }
  };

  const clearFilters = () => {
    setSearchTerm('');
    setFilterGender('all');
    setFilterBloodGroup('all');
  };

  const openEditPatient = (patient) => {
    setSelectedPatient(patient);
    setEditPatientForm({
      first_name: patient.first_name || '',
      last_name: patient.last_name || '',
      date_of_birth: patient.date_of_birth || '',
      age: patient.age != null ? String(patient.age) : '',
      gender: patient.gender || '',
      blood_group: patient.blood_group || '',
      marital_status: patient.marital_status || '',
      abha_id: patient.abha_id || '',
      email: patient.email || '',
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
          updateData[key] = key === 'age' ? parseInt(value) : value;
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

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  const formatAge = (dateString) => {
    if (!dateString) return 'N/A';
    const birthDate = new Date(dateString);
    const today = new Date();
    const age = today.getFullYear() - birthDate.getFullYear();
    const monthDiff = today.getMonth() - birthDate.getMonth();
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
      return age - 1;
    }
    return age;
  };

  const fetchAppointmentHistory = async (patientId) => {
    setHistoryLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/patient/${patientId}/history`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        setAppointmentHistory(data.appointments || []);
      } else {
        setAppointmentHistory([]);
      }
    } catch (error) {
      console.error('Error fetching history:', error);
      setAppointmentHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const formatTimeStr = (timeStr) => {
    if (!timeStr) return '';
    try {
      const [hours, minutes] = timeStr.split(':');
      const h = parseInt(hours);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const h12 = h % 12 || 12;
      return `${h12}:${minutes} ${ampm}`;
    } catch {
      return timeStr;
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      'scheduled': 'bg-blue-100 text-blue-800',
      'confirmed': 'bg-green-100 text-green-800',
      'in_progress': 'bg-yellow-100 text-yellow-800',
      'completed': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800',
      'no_show': 'bg-red-100 text-red-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
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
          <Dialog open={showPatientDialog} onOpenChange={setShowPatientDialog}>
            <DialogTrigger asChild>
              <Button className="flex items-center space-x-2">
                <UserPlus className="h-4 w-4" />
                <span>Register Patient</span>
              </Button>
            </DialogTrigger>
          </Dialog>
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
          <CardTitle>Patients ({filteredPatients.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin mr-2" />
              <span>Loading patients...</span>
            </div>
          ) : filteredPatients.length === 0 ? (
            <div className="text-center py-8">
              <User className="h-12 w-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-500 mb-3">
                {searchTerm || (filterGender && filterGender !== 'all') || (filterBloodGroup && filterBloodGroup !== 'all') 
                  ? 'No patients found matching your criteria'
                  : 'No patients registered yet'
                }
              </p>
              <Dialog open={showPatientDialog} onOpenChange={setShowPatientDialog}>
                <DialogTrigger asChild>
                  <Button>
                    <UserPlus className="h-4 w-4 mr-2" />
                    Register First Patient
                  </Button>
                </DialogTrigger>
              </Dialog>
            </div>
          ) : (
            <>
              <div className="text-xs text-gray-500 mb-2">
                Showing {Math.min((currentPage - 1) * patientsPerPage + 1, filteredPatients.length)}–{Math.min(currentPage * patientsPerPage, filteredPatients.length)} of {filteredPatients.length} patients
              </div>
              <div className="space-y-3">
                {filteredPatients.slice((currentPage - 1) * patientsPerPage, currentPage * patientsPerPage).map((patient) => (
                  <div key={patient.patient_id} className={`border rounded-lg p-4 hover:bg-gray-50 ${patient._isMatch ? 'bg-yellow-50 border-yellow-200' : ''}`}>
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
                          {(patient.date_of_birth || patient.age) && (
                            <p className="text-sm text-gray-600">
                              Age: {patient.date_of_birth ? formatAge(patient.date_of_birth) : patient.age} years
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
                        <Button size="sm" variant="outline" onClick={() => {
                          setSelectedPatient(patient);
                          fetchAppointmentHistory(patient.patient_id);
                          setShowHistoryDialog(true);
                        }}>
                          History
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEditPatient(patient)}>
                          Edit
                        </Button>
                        <Button size="sm" onClick={() => {
                          navigate('/dashboard/reception/appointments');
                        }}>
                          Create Appointment
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {Math.ceil(filteredPatients.length / patientsPerPage) > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <Button
                    variant="outline" size="sm"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(prev => prev - 1)}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" /> Previous
                  </Button>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.ceil(filteredPatients.length / patientsPerPage) }, (_, i) => i + 1)
                      .filter(page => page === 1 || page === Math.ceil(filteredPatients.length / patientsPerPage) || Math.abs(page - currentPage) <= 2)
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
                    disabled={currentPage >= Math.ceil(filteredPatients.length / patientsPerPage)}
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

      {/* Register Patient Dialog */}
      <Dialog open={showPatientDialog} onOpenChange={setShowPatientDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register New Patient</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="first_name">First Name *</Label>
              <Input
                id="first_name"
                value={patientForm.first_name}
                onChange={(e) => setPatientForm({...patientForm, first_name: e.target.value})}
                required
              />
            </div>
            <div>
              <Label htmlFor="last_name">Last Name *</Label>
              <Input
                id="last_name"
                value={patientForm.last_name}
                onChange={(e) => setPatientForm({...patientForm, last_name: e.target.value})}
                required
              />
            </div>
            <div>
              <Label htmlFor="date_of_birth">Date of Birth</Label>
              <Input
                id="date_of_birth"
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
                  setPatientForm(prev => ({...prev, ...updates}));
                }}
              />
            </div>
            <div>
              <Label htmlFor="age">Age (years)</Label>
              <Input
                id="age"
                type="number"
                min="0"
                max="150"
                placeholder="Enter age"
                value={patientForm.age}
                onChange={(e) => setPatientForm({...patientForm, age: e.target.value, date_of_birth: ''})}
              />
            </div>
            <div>
              <Label htmlFor="gender">Gender</Label>
              <Select value={patientForm.gender} onValueChange={(value) => setPatientForm({...patientForm, gender: value})}>
                <SelectTrigger>
                  <SelectValue placeholder="Select Gender" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Male">Male</SelectItem>
                  <SelectItem value="Female">Female</SelectItem>
                  <SelectItem value="Other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="blood_group">Blood Group</Label>
              <Select value={patientForm.blood_group} onValueChange={(value) => setPatientForm({...patientForm, blood_group: value})}>
                <SelectTrigger>
                  <SelectValue placeholder="Select Blood Group" />
                </SelectTrigger>
                <SelectContent>
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
              <Select value={patientForm.marital_status} onValueChange={(value) => setPatientForm({...patientForm, marital_status: value})}>
                <SelectTrigger><SelectValue placeholder="Select Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Single">Single</SelectItem>
                  <SelectItem value="Married">Married</SelectItem>
                  <SelectItem value="Widowed">Widowed</SelectItem>
                  <SelectItem value="Divorced">Divorced</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>ABHA ID</Label>
              <Input value={patientForm.abha_id} onChange={(e) => setPatientForm({...patientForm, abha_id: e.target.value})} placeholder="14-digit ABHA number" />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={patientForm.email} onChange={(e) => setPatientForm({...patientForm, email: e.target.value})} placeholder="patient@email.com" />
            </div>
            <div>
              <Label htmlFor="primary_phone">Primary Phone *</Label>
              <Input
                id="primary_phone"
                value={patientForm.primary_phone}
                onChange={(e) => setPatientForm({...patientForm, primary_phone: e.target.value})}
                required
              />
            </div>
            <div>
              <Label htmlFor="referred_by">Referred By</Label>
              <Input
                id="referred_by"
                value={patientForm.referred_by}
                onChange={(e) => setPatientForm({...patientForm, referred_by: e.target.value})}
                placeholder="Referring doctor / person name"
              />
            </div>

            {/* Emergency Contact Section */}
            <div className="col-span-2 border-t pt-3 mt-2">
              <Label className="text-sm font-semibold text-gray-700">Emergency Contact</Label>
            </div>
            <div>
              <Label>Contact Name</Label>
              <Input value={patientForm.emergency_contact_name} onChange={(e) => setPatientForm({...patientForm, emergency_contact_name: e.target.value})} placeholder="Emergency contact name" />
            </div>
            <div>
              <Label>Contact Phone</Label>
              <Input value={patientForm.emergency_contact_phone} onChange={(e) => setPatientForm({...patientForm, emergency_contact_phone: e.target.value})} placeholder="Phone number" />
            </div>
            <div>
              <Label>Relation</Label>
              <Select value={patientForm.emergency_contact_relation} onValueChange={(value) => setPatientForm({...patientForm, emergency_contact_relation: value})}>
                <SelectTrigger><SelectValue placeholder="Select Relation" /></SelectTrigger>
                <SelectContent>
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
            <div className="col-span-2 border-t pt-3 mt-2">
              <Label className="text-sm font-semibold text-gray-700">Address</Label>
            </div>
            <div className="col-span-2">
              <Label>Address Line 1</Label>
              <Input value={patientForm.address_line1} onChange={(e) => setPatientForm({...patientForm, address_line1: e.target.value})} placeholder="House/Flat No, Street" />
            </div>
            <div className="col-span-2">
              <Label>Address Line 2</Label>
              <Input value={patientForm.address_line2} onChange={(e) => setPatientForm({...patientForm, address_line2: e.target.value})} placeholder="Area, Landmark" />
            </div>
            <div>
              <Label>Village / Town</Label>
              <Input value={patientForm.village} onChange={(e) => setPatientForm({...patientForm, village: e.target.value})} />
            </div>
            <div>
              <Label>Mandal / Taluka</Label>
              <Input value={patientForm.mandal} onChange={(e) => setPatientForm({...patientForm, mandal: e.target.value})} />
            </div>
            <div>
              <Label>District</Label>
              <Input value={patientForm.district} onChange={(e) => setPatientForm({...patientForm, district: e.target.value})} />
            </div>
          </div>
          <div className="flex gap-2 pt-4">
            <Button variant="outline" onClick={() => setShowPatientDialog(false)} className="flex-1">
              Cancel
            </Button>
            <Button
              onClick={createPatient}
              disabled={loading || !patientForm.first_name || !patientForm.last_name || !patientForm.primary_phone}
              className="flex-1"
            >
              {loading ? 'Registering...' : 'Register Patient'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Patient Dialog */}
      <Dialog open={showEditPatientDialog} onOpenChange={setShowEditPatientDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Patient - {selectedPatient?.first_name} {selectedPatient?.last_name}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4">
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
                  setEditPatientForm(prev => ({...prev, ...updates}));
                }}
              />
            </div>
            <div>
              <Label>Age (years)</Label>
              <Input
                type="number"
                min="0"
                max="150"
                placeholder="Enter age"
                value={editPatientForm.age}
                onChange={(e) => setEditPatientForm({...editPatientForm, age: e.target.value, date_of_birth: ''})}
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
              <Label>Email</Label>
              <Input type="email" value={editPatientForm.email} onChange={(e) => setEditPatientForm({...editPatientForm, email: e.target.value})} placeholder="patient@email.com" />
            </div>
            <div>
              <Label>Referred By</Label>
              <Input value={editPatientForm.referred_by || ''} onChange={(e) => setEditPatientForm({...editPatientForm, referred_by: e.target.value})} placeholder="Referring doctor / person name" />
            </div>

            {/* Emergency Contact Section */}
            <div className="col-span-2 border-t pt-3 mt-2">
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
            <div className="col-span-2 border-t pt-3 mt-2">
              <Label className="text-sm font-semibold text-gray-700">Address</Label>
            </div>
            <div className="col-span-2">
              <Label>Address Line 1</Label>
              <Input value={editPatientForm.address_line1} onChange={(e) => setEditPatientForm({...editPatientForm, address_line1: e.target.value})} placeholder="House/Flat No, Street" />
            </div>
            <div className="col-span-2">
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
          <div className="flex gap-2 pt-4">
            <Button variant="outline" onClick={() => setShowEditPatientDialog(false)} className="flex-1">
              Cancel
            </Button>
            <Button
              onClick={handleUpdatePatient}
              disabled={loading || !editPatientForm.first_name || !editPatientForm.last_name}
              className="flex-1"
            >
              {loading ? 'Updating...' : 'Update Patient'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Vitals Dialog */}
      <Dialog open={showVitalsDialog} onOpenChange={setShowVitalsDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Record Vitals - {selectedPatient?.first_name} {selectedPatient?.last_name}</DialogTitle>
          </DialogHeader>
          {selectedPatient && (
            <VitalsForm
              patient={selectedPatient}
              onSuccess={() => {
                setShowVitalsDialog(false);
                toast({ title: 'Success', description: 'Vitals recorded successfully!' });
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Visit History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Visit History - {selectedPatient?.first_name} {selectedPatient?.last_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {historyLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                <span>Loading history...</span>
              </div>
            ) : appointmentHistory.length === 0 ? (
              <div className="text-center py-8">
                <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-500">No appointment history found</p>
              </div>
            ) : (
              appointmentHistory.map((apt) => (
                <div key={apt.id} className="border rounded-lg p-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium">{apt.appointment_date ? new Date(apt.appointment_date).toLocaleDateString() : 'N/A'}</span>
                        <span className="text-sm text-gray-500">{formatTimeStr(apt.appointment_time)}</span>
                        {apt.token_number && (
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-800 font-bold text-xs">
                            {apt.token_number}
                          </span>
                        )}
                        <Badge className={getStatusColor(apt.status)}>{apt.status}</Badge>
                      </div>
                      <p className="text-sm">{apt.doctor_name} {apt.doctor_specialization ? `(${apt.doctor_specialization})` : ''}</p>
                      <p className="text-sm text-gray-500">{apt.appointment_type}{apt.reason ? ` - ${apt.reason}` : ''}</p>
                      {apt.notes && <p className="text-sm text-gray-600 mt-1 italic">Notes: {apt.notes}</p>}
                      {apt.cancellation_reason && <p className="text-xs text-red-500">Cancelled: {apt.cancellation_reason}</p>}
                    </div>
                    <div className="text-right text-sm">
                      {apt.final_amount > 0 && <p className="font-medium text-green-600">₹{apt.final_amount}</p>}
                      {apt.payment_status && <Badge variant="outline" className="text-xs">{apt.payment_status}</Badge>}
                    </div>
                  </div>
                </div>
              ))
            )}
            <div className="flex justify-end pt-2">
              <Button variant="outline" onClick={() => setShowHistoryDialog(false)}>Close</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prescriptions Dialog */}
      <Dialog open={showPrescriptionsDialog} onOpenChange={setShowPrescriptionsDialog}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Prescriptions - {selectedPatient?.first_name} {selectedPatient?.last_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {prescriptionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-6 w-6 animate-spin mr-2" />
                <span>Loading prescriptions...</span>
              </div>
            ) : prescriptions.length === 0 ? (
              <div className="text-center py-8">
                <Pill className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-500">No prescriptions found for this patient</p>
              </div>
            ) : (
              <div className="space-y-4">
                {prescriptions.map((prescription) => (
                  <Card key={prescription.prescription_id}>
                    <CardHeader className="pb-3">
                      <div className="flex justify-between items-start">
                        <div>
                          <h6 className="font-semibold">RX-{prescription.prescription_number}</h6>
                          <div className="flex items-center gap-4 text-sm text-gray-500">
                            <p>
                              <User className="h-3 w-3 inline mr-1" />
                              Doctor: {prescription.doctor_name}
                            </p>
                            <p>Date: {new Date(prescription.prescription_date).toLocaleDateString()}</p>
                            {prescription.diagnosis && (
                              <p className="text-blue-700 font-medium">
                                Diagnosis: {prescription.diagnosis}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <Button size="sm" variant="outline"
                            onClick={() => printPrescription(prescription.prescription_id, true)}>
                            With Header
                          </Button>
                          <Button size="sm" variant="ghost"
                            onClick={() => printPrescription(prescription.prescription_id, false)}>
                            Without Header
                          </Button>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <h6 className="font-medium text-sm">Medicines:</h6>
                        <div className="grid gap-3">
                          {prescription.medicines.map((medicine, index) => (
                            <div key={index} className="bg-gray-50 rounded-lg p-3">
                              <div className="flex justify-between items-start">
                                <div className="flex-1">
                                  <p className="font-medium">{medicine.name}</p>
                                  <p><strong>Dosage:</strong> {medicine.dosage}</p>
                                  <p><strong>Duration:</strong> {medicine.duration}</p>
                                  <p><strong>Quantity:</strong> {medicine.quantity}</p>
                                  {medicine.instructions && (
                                    <p><strong>Instructions:</strong> {medicine.instructions}</p>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {prescription.notes && (
                        <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                          <h6 className="font-medium text-sm text-blue-800 mb-1">Notes:</h6>
                          <p className="text-sm text-blue-700">{prescription.notes}</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
            
            <div className="flex justify-end pt-4">
              <Button variant="outline" onClick={() => setShowPrescriptionsDialog(false)}>
                Close
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReceptionPatientsPage;