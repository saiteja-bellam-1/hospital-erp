import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../components/ui/dialog';
import { 
  Search, 
  Calendar,
  User,
  Phone,
  MapPin,
  Clock,
  Receipt,
  Filter,
  UserPlus,
  Eye,
  RefreshCw,
  Activity,
  Pill,
  Printer
} from 'lucide-react';
import BillingManager from '../../components/billing/BillingManager';
import VitalsForm from '../../components/vitals/VitalsForm';
import { useToast } from '../../hooks/use-toast';

const ReceptionistDashboard = () => {
  const { toast } = useToast();
  const [patients, setPatients] = useState([]);
  const [filteredPatients, setFilteredPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [doctors, setDoctors] = useState([]);
  const [todayAppointments, setTodayAppointments] = useState([]);
  
  // Dialogs
  const [showPatientDialog, setShowPatientDialog] = useState(false);
  const [showAppointmentDialog, setShowAppointmentDialog] = useState(false);
  const [showBillingDialog, setShowBillingDialog] = useState(false);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const [showPrescriptionsDialog, setShowPrescriptionsDialog] = useState(false);
  const [selectedConsultation, setSelectedConsultation] = useState(null);
  
  // Prescription state
  const [prescriptions, setPrescriptions] = useState([]);
  const [prescriptionsLoading, setPrescriptionsLoading] = useState(false);

  // Bill preview state
  const [showBillPreviewDialog, setShowBillPreviewDialog] = useState(false);
  const [currentBill, setCurrentBill] = useState(null);
  const [billPdfUrl, setBillPdfUrl] = useState(null);
  const [billIncludeHeader, setBillIncludeHeader] = useState(true);
  const [currentBillAppointmentId, setCurrentBillAppointmentId] = useState(null);

  // Filter states
  const [filterGender, setFilterGender] = useState('all');
  const [filterBloodGroup, setFilterBloodGroup] = useState('all');
  const [showFilters, setShowFilters] = useState(false);

  // Forms
  const [patientForm, setPatientForm] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
    age: '',
    gender: '',
    blood_group: '',
    primary_phone: '',
    emergency_contact_phone: '',
    address: ''
  });

  const [appointmentForm, setAppointmentForm] = useState({
    doctor_id: '',
    appointment_date: '',
    appointment_time: '',
    duration_minutes: 30,
    appointment_type: 'consultation',
    reason: '',
    priority: 'normal',
    payment_status: 'paid',
    payment_method: 'cash',
    discount_amount: 0,
    payment_notes: ''
  });

  // Load initial data
  useEffect(() => {
    fetchPatients();
    fetchDoctors();
    fetchTodayAppointments();
  }, []);

  // Filter patients based on search term and filters
  useEffect(() => {
    let filtered = patients;

    // Search filter
    if (searchTerm) {
      filtered = filtered.filter(patient => 
        patient.first_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        patient.last_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        patient.primary_phone?.includes(searchTerm) ||
        patient.patient_id?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Gender filter
    if (filterGender && filterGender !== 'all') {
      filtered = filtered.filter(patient => patient.gender === filterGender);
    }

    // Blood group filter
    if (filterBloodGroup && filterBloodGroup !== 'all') {
      filtered = filtered.filter(patient => patient.blood_group === filterBloodGroup);
    }

    setFilteredPatients(filtered);
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

  const fetchDoctors = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/doctors', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setDoctors(data);
      }
    } catch (error) {
      console.error('Error fetching doctors:', error);
    }
  };

  const fetchTodayAppointments = async () => {
    try {
      const token = localStorage.getItem('token');
      const today = new Date().toISOString().split('T')[0];
      console.log('Fetching appointments for:', today); // Debug log
      const response = await fetch(`/api/appointments/?date_from=${today}&date_to=${today}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        console.log('Appointments fetched:', data); // Debug log
        setTodayAppointments(Array.isArray(data) ? data : []);
      } else {
        console.error('Failed to fetch appointments:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('Error fetching today appointments:', error);
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
        body: JSON.stringify(Object.fromEntries(
          Object.entries({
            ...patientForm,
            age: patientForm.age ? parseInt(patientForm.age) : null,
            date_of_birth: patientForm.date_of_birth || null,
          }).map(([k, v]) => [k, v === '' ? null : v])
        ))
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
          primary_phone: '',
          emergency_contact_phone: '',
          address: ''
        });
      }
    } catch (error) {
      console.error('Error creating patient:', error);
    } finally {
      setLoading(false);
    }
  };

  const createAppointment = async () => {
    if (!selectedPatient) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          patient_id: selectedPatient.patient_id,
          ...appointmentForm
        })
      });

      if (response.ok) {
        const appointmentData = await response.json();
        setShowAppointmentDialog(false);
        fetchTodayAppointments();
        setAppointmentForm({
          doctor_id: '',
          appointment_date: '',
          appointment_time: '',
          duration_minutes: 30,
          appointment_type: 'consultation',
          reason: '',
          priority: 'normal',
          payment_status: 'paid',
          payment_method: 'cash',
          discount_amount: 0,
          payment_notes: ''
        });
        
        // Show bill preview if consultation fee exists
        if (appointmentData.consultation_fee > 0) {
          showBillPreview(appointmentData.id);
        } else {
          toast({ title: 'Success', description: 'Appointment booked successfully!' });
        }
      } else {
        const errorData = await response.json();
        console.error('Appointment creation failed:', errorData);
        toast({ title: 'Error', description: `Failed to book appointment: ${errorData.detail || 'Unknown error'}`, variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error creating appointment:', error);
    } finally {
      setLoading(false);
    }
  };

  // Bill preview functions
  const showBillPreview = async (appointmentId, includeHeader = true) => {
    try {
      const token = localStorage.getItem('token');
      setCurrentBillAppointmentId(appointmentId);
      setBillIncludeHeader(includeHeader);

      // Fetch bill data
      const billResponse = await fetch(`/api/appointments/${appointmentId}/bill`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (billResponse.ok) {
        const billData = await billResponse.json();
        setCurrentBill(billData);
        
        // Fetch PDF for preview
        const pdfResponse = await fetch(`/api/appointments/${appointmentId}/bill/download?include_header=${includeHeader}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        if (pdfResponse.ok) {
          const blob = await pdfResponse.blob();
          const url = window.URL.createObjectURL(blob);
          setBillPdfUrl(url);
          setShowBillPreviewDialog(true);
        }
      }
    } catch (error) {
      console.error('Error fetching bill:', error);
      toast({ title: 'Error', description: 'Failed to load bill preview', variant: 'destructive' });
    }
  };

  const printBill = () => {
    if (billPdfUrl) {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
      iframe.src = billPdfUrl;
      
      iframe.onload = () => {
        iframe.contentWindow.print();
        setTimeout(() => {
          document.body.removeChild(iframe);
        }, 1000);
      };
    }
  };

  const closeBillPreview = () => {
    setShowBillPreviewDialog(false);
    if (billPdfUrl) {
      window.URL.revokeObjectURL(billPdfUrl);
      setBillPdfUrl(null);
    }
    setCurrentBill(null);
  };

  const getStatusBadge = (status) => {
    const colors = {
      'scheduled': 'bg-blue-100 text-blue-800',
      'confirmed': 'bg-green-100 text-green-800',
      'in_progress': 'bg-yellow-100 text-yellow-800',
      'completed': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800'
    };
    return <Badge className={colors[status] || 'bg-gray-100 text-gray-800'}>{status}</Badge>;
  };

  const fetchPatientPrescriptions = async (patientId) => {
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
          // Clean up after printing
          setTimeout(() => {
            document.body.removeChild(iframe);
            window.URL.revokeObjectURL(url);
          }, 1000);
        };
      } else {
        toast({ title: 'Error', description: 'Failed to print prescription', variant: 'destructive' });
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
    setShowFilters(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Reception Dashboard</h1>
          <p className="text-gray-600">Manage patients, appointments, and billing</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchPatients} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Dialog open={showPatientDialog} onOpenChange={setShowPatientDialog}>
            <DialogTrigger asChild>
              <Button>
                <UserPlus className="h-4 w-4 mr-2" />
                New Patient
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Register New Patient</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>First Name *</Label>
                    <Input
                      value={patientForm.first_name}
                      onChange={(e) => setPatientForm({...patientForm, first_name: e.target.value})}
                      placeholder="Enter first name"
                    />
                  </div>
                  <div>
                    <Label>Last Name *</Label>
                    <Input
                      value={patientForm.last_name}
                      onChange={(e) => setPatientForm({...patientForm, last_name: e.target.value})}
                      placeholder="Enter last name"
                    />
                  </div>
                </div>

                <div>
                  <Label>Primary Phone *</Label>
                  <Input
                    value={patientForm.primary_phone}
                    onChange={(e) => setPatientForm({...patientForm, primary_phone: e.target.value})}
                    placeholder="Enter phone number"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Date of Birth</Label>
                    <Input
                      type="date"
                      value={patientForm.date_of_birth}
                      onChange={(e) => setPatientForm({...patientForm, date_of_birth: e.target.value, age: ''})}
                    />
                  </div>
                  <div>
                    <Label>Age (if DOB unknown)</Label>
                    <Input
                      type="number"
                      value={patientForm.age}
                      onChange={(e) => setPatientForm({...patientForm, age: e.target.value, date_of_birth: ''})}
                      placeholder="Age in years"
                    />
                  </div>
                  <div>
                    <Label>Gender</Label>
                    <Select
                      value={patientForm.gender}
                      onValueChange={(value) => setPatientForm({...patientForm, gender: value})}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select gender" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Male">Male</SelectItem>
                        <SelectItem value="Female">Female</SelectItem>
                        <SelectItem value="Other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Blood Group</Label>
                    <Select
                      value={patientForm.blood_group}
                      onValueChange={(value) => setPatientForm({...patientForm, blood_group: value})}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select blood group" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="A+">A+</SelectItem>
                        <SelectItem value="A-">A-</SelectItem>
                        <SelectItem value="B+">B+</SelectItem>
                        <SelectItem value="B-">B-</SelectItem>
                        <SelectItem value="O+">O+</SelectItem>
                        <SelectItem value="O-">O-</SelectItem>
                        <SelectItem value="AB+">AB+</SelectItem>
                        <SelectItem value="AB-">AB-</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Emergency Contact</Label>
                    <Input
                      value={patientForm.emergency_contact_phone}
                      onChange={(e) => setPatientForm({...patientForm, emergency_contact_phone: e.target.value})}
                      placeholder="Emergency phone"
                    />
                  </div>
                </div>

                <div>
                  <Label>Address</Label>
                  <Textarea
                    value={patientForm.address}
                    onChange={(e) => setPatientForm({...patientForm, address: e.target.value})}
                    placeholder="Enter address"
                  />
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setShowPatientDialog(false)} className="flex-1">
                    Cancel
                  </Button>
                  <Button onClick={createPatient} disabled={loading || !patientForm.first_name || !patientForm.primary_phone} className="flex-1">
                    {loading ? 'Creating...' : 'Register Patient'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <Label>Search Patients</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                  <Input
                    placeholder="Search by name, phone, or patient ID..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Button
                  variant="outline"
                  onClick={() => setShowFilters(!showFilters)}
                  className="flex items-center gap-2"
                >
                  <Filter className="h-4 w-4" />
                  Filters
                </Button>
                {(searchTerm || (filterGender && filterGender !== 'all') || (filterBloodGroup && filterBloodGroup !== 'all')) && (
                  <Button variant="outline" onClick={clearFilters}>
                    Clear
                  </Button>
                )}
              </div>
            </div>
          </div>

          {/* Advanced Filters */}
          {showFilters && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Gender</Label>
                  <Select value={filterGender} onValueChange={setFilterGender}>
                    <SelectTrigger>
                      <SelectValue placeholder="All genders" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All genders</SelectItem>
                      <SelectItem value="Male">Male</SelectItem>
                      <SelectItem value="Female">Female</SelectItem>
                      <SelectItem value="Other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Blood Group</Label>
                  <Select value={filterBloodGroup} onValueChange={setFilterBloodGroup}>
                    <SelectTrigger>
                      <SelectValue placeholder="All blood groups" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All blood groups</SelectItem>
                      <SelectItem value="A+">A+</SelectItem>
                      <SelectItem value="A-">A-</SelectItem>
                      <SelectItem value="B+">B+</SelectItem>
                      <SelectItem value="B-">B-</SelectItem>
                      <SelectItem value="O+">O+</SelectItem>
                      <SelectItem value="O-">O-</SelectItem>
                      <SelectItem value="AB+">AB+</SelectItem>
                      <SelectItem value="AB-">AB-</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Patients List */}
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
                  {searchTerm && (
                    <Button
                      variant="outline"
                      onClick={() => setShowPatientDialog(true)}
                      className="mt-2"
                    >
                      Register New Patient
                    </Button>
                  )}
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
                              {patient.address && (
                                <p className="flex items-center gap-1">
                                  <MapPin className="h-3 w-3" />
                                  {patient.address.substring(0, 30)}...
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-1">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedPatient(patient);
                                setShowVitalsDialog(true);
                              }}
                              title="Record Vitals"
                            >
                              <Activity className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedPatient(patient);
                                setShowAppointmentDialog(true);
                              }}
                              title="Book Appointment"
                            >
                              <Calendar className="h-3 w-3" />
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

        {/* Today's Appointments */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                Today's Appointments ({todayAppointments.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {todayAppointments.length === 0 ? (
                <p className="text-gray-500 text-center py-4">No appointments today</p>
              ) : (
                <div className="space-y-3 max-h-80 overflow-y-auto">
                  {todayAppointments.map((appointment) => (
                    <Card key={appointment.id} className="border-l-4 border-l-blue-500">
                      <CardContent className="pt-3 pb-3">
                        <div className="space-y-2">
                          <div className="flex justify-between items-start">
                            <div>
                              <p className="font-medium text-sm">{appointment.patient_name}</p>
                              <p className="text-xs text-gray-600">{appointment.doctor_name}</p>
                            </div>
                            {getStatusBadge(appointment.status)}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-gray-600">
                            <Clock className="h-3 w-3" />
                            {appointment.appointment_time}
                          </div>
                          {appointment.reason && (
                            <p className="text-xs text-gray-500">{appointment.reason}</p>
                          )}
                          <div className="flex gap-1">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setSelectedConsultation({
                                  id: appointment.consultation_id || appointment.id,
                                  patient_name: appointment.patient_name,
                                  doctor_name: appointment.doctor_name
                                });
                                setShowBillingDialog(true);
                              }}
                            >
                              <Receipt className="h-3 w-3" />
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

          {/* Quick Actions */}
          {selectedPatient && (
            <Card>
              <CardHeader>
                <CardTitle>Quick Actions</CardTitle>
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
                  onClick={() => setShowAppointmentDialog(true)}
                  className="w-full flex items-center gap-2"
                >
                  <Calendar className="h-4 w-4" />
                  Book Appointment
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    fetchPatientPrescriptions(selectedPatient.patient_id);
                    setShowPrescriptionsDialog(true);
                  }}
                  className="w-full flex items-center gap-2"
                >
                  <Pill className="h-4 w-4" />
                  View Prescriptions
                </Button>
                <Button
                  variant="outline"
                  onClick={() => searchPatientByPhone(selectedPatient.primary_phone)}
                  className="w-full flex items-center gap-2"
                >
                  <Eye className="h-4 w-4" />
                  View Details
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Appointment Dialog */}
      <Dialog open={showAppointmentDialog} onOpenChange={setShowAppointmentDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Book Appointment</DialogTitle>
            {selectedPatient && (
              <p className="text-sm text-gray-600">
                Patient: {selectedPatient.first_name} {selectedPatient.last_name}
              </p>
            )}
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Doctor *</Label>
                <Select
                  value={appointmentForm.doctor_id}
                  onValueChange={(value) => setAppointmentForm({...appointmentForm, doctor_id: value})}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select doctor" />
                  </SelectTrigger>
                  <SelectContent>
                    {doctors.map((doctor) => (
                      <SelectItem key={doctor.id} value={doctor.id.toString()}>
                        Dr. {doctor.first_name} {doctor.last_name} - {doctor.specialization}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Date *</Label>
                <Input
                  type="date"
                  value={appointmentForm.appointment_date}
                  onChange={(e) => setAppointmentForm({...appointmentForm, appointment_date: e.target.value})}
                  min={new Date().toISOString().split('T')[0]}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Time *</Label>
                <Input
                  type="time"
                  value={appointmentForm.appointment_time}
                  onChange={(e) => setAppointmentForm({...appointmentForm, appointment_time: e.target.value})}
                />
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select
                  value={appointmentForm.payment_method}
                  onValueChange={(value) => setAppointmentForm({...appointmentForm, payment_method: value})}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="insurance">Insurance</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label>Reason for Visit</Label>
              <Textarea
                value={appointmentForm.reason}
                onChange={(e) => setAppointmentForm({...appointmentForm, reason: e.target.value})}
                placeholder="Enter reason for appointment"
              />
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setShowAppointmentDialog(false)} className="flex-1">
                Cancel
              </Button>
              <Button
                onClick={createAppointment}
                disabled={loading || !appointmentForm.doctor_id || !appointmentForm.appointment_date || !appointmentForm.appointment_time}
                className="flex-1"
              >
                {loading ? 'Booking...' : 'Book Appointment'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Billing Dialog */}
      <Dialog open={showBillingDialog} onOpenChange={setShowBillingDialog}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Billing Management</DialogTitle>
          </DialogHeader>
          {selectedConsultation && (
            <BillingManager
              consultation={selectedConsultation}
              onPaymentUpdate={(payment) => {
                console.log('Payment processed:', payment);
                fetchTodayAppointments();
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Vitals Dialog */}
      <VitalsForm
        isOpen={showVitalsDialog}
        onClose={() => setShowVitalsDialog(false)}
        selectedPatient={selectedPatient}
        userRole="receptionist"
        onSave={(vitalsData) => {
          console.log('Vitals saved:', vitalsData);
          // Could refresh patient data here if needed
        }}
      />

      {/* Prescriptions Dialog */}
      <Dialog open={showPrescriptionsDialog} onOpenChange={setShowPrescriptionsDialog}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pill className="h-5 w-5" />
              Patient Prescriptions
              {selectedPatient && (
                <span className="text-sm font-normal text-gray-600">
                  - {selectedPatient.first_name} {selectedPatient.last_name}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            {prescriptionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-3">Loading prescriptions...</span>
              </div>
            ) : prescriptions.length === 0 ? (
              <div className="text-center py-8">
                <Pill className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">No prescriptions found for this patient</p>
              </div>
            ) : (
              <div className="space-y-4">
                {prescriptions.map((prescription) => (
                  <Card key={prescription.id} className="border-l-4 border-l-green-500">
                    <CardContent className="pt-4">
                      <div className="flex justify-between items-start mb-4">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <h4 className="font-semibold">{prescription.prescription_id}</h4>
                            <Badge className={prescription.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                              {prescription.status.toUpperCase()}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600">
                            <User className="h-3 w-3 inline mr-1" />
                            Doctor: {prescription.doctor_name}
                          </p>
                          <p className="text-xs text-gray-500">
                            Date: {new Date(prescription.prescription_date).toLocaleDateString()}
                          </p>
                          {prescription.diagnosis && (
                            <p className="text-sm text-blue-700 font-medium">
                              Diagnosis: {prescription.diagnosis}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-1">
                          <Button size="sm" variant="outline" className="flex items-center gap-1"
                            onClick={() => printPrescription(prescription.prescription_id, true)}>
                            <Printer className="h-3.5 w-3.5" /> With Header
                          </Button>
                          <Button size="sm" variant="ghost"
                            onClick={() => printPrescription(prescription.prescription_id, false)}>
                            Without Header
                          </Button>
                        </div>
                      </div>
                      
                      {/* Medicines */}
                      <div className="space-y-3">
                        <h5 className="font-medium text-sm text-gray-700">Medicines:</h5>
                        <div className="grid gap-3">
                          {prescription.medicines.map((medicine, index) => (
                            <div key={index} className="bg-gray-50 p-3 rounded-lg">
                              <div className="flex justify-between items-start">
                                <div className="space-y-1">
                                  <p className="font-medium text-sm">{medicine.name}</p>
                                  <div className="text-xs text-gray-600 space-y-1">
                                    <p><strong>Dosage:</strong> {medicine.dosage}</p>
                                    <p><strong>Duration:</strong> {medicine.duration}</p>
                                    {medicine.quantity && (
                                      <p><strong>Quantity:</strong> {medicine.quantity}</p>
                                    )}
                                    {medicine.instructions && (
                                      <p><strong>Instructions:</strong> {medicine.instructions}</p>
                                    )}
                                  </div>
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

      {/* Bill Preview Dialog */}
      <Dialog open={showBillPreviewDialog} onOpenChange={closeBillPreview}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" />
              Bill Preview - {currentBill?.bill_number}
            </DialogTitle>
          </DialogHeader>
          
          <div className="flex flex-col space-y-4 h-full">
            {/* Bill Summary */}
            {currentBill && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-600">Patient</p>
                  <p className="font-semibold">{currentBill.patient_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Doctor</p>
                  <p className="font-semibold">{currentBill.doctor_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Total Amount</p>
                  <p className="font-semibold text-green-600">₹{currentBill.total_amount?.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Payment Status</p>
                  <Badge variant={currentBill.balance_due === 0 ? "success" : "secondary"}>
                    {currentBill.balance_due === 0 ? "Paid" : "Pending"}
                  </Badge>
                </div>
              </div>
            )}
            
            {/* PDF Preview */}
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {billPdfUrl && (
                <iframe
                  src={billPdfUrl}
                  className="w-full h-full border-0"
                  title="Bill Preview"
                />
              )}
            </div>
            
            {/* Action Buttons */}
            <div className="flex items-center gap-3 pt-4">
              <div className="flex items-center space-x-2">
                <input type="checkbox" id="bill-header-rcpt" checked={billIncludeHeader}
                  onChange={async (e) => {
                    const newVal = e.target.checked;
                    setBillIncludeHeader(newVal);
                    if (currentBillAppointmentId) {
                      if (billPdfUrl) { window.URL.revokeObjectURL(billPdfUrl); setBillPdfUrl(null); }
                      await showBillPreview(currentBillAppointmentId, newVal);
                    }
                  }}
                  className="w-4 h-4" />
                <Label htmlFor="bill-header-rcpt" className="text-sm">Include header</Label>
              </div>
              <Button variant="outline" onClick={closeBillPreview} className="flex-1">
                Close
              </Button>
              <Button onClick={printBill} className="flex-1 bg-blue-600 hover:bg-blue-700">
                <Printer className="h-4 w-4 mr-2" />
                Print Bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReceptionistDashboard;