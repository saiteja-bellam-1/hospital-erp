import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../components/ui/dialog';
import { Plus, Search, Calendar as CalendarIcon, Clock, User, Trash2 } from 'lucide-react';
import { format } from 'date-fns';
import { useToast } from '../../hooks/use-toast';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';

const OutpatientModule = () => {
  const { toast } = useToast();
  const [confirmState, setConfirmState] = useState({ open: false });
  const [activeTab, setActiveTab] = useState('reception');
  const [appointments, setAppointments] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [searchPhone, setSearchPhone] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  
  // Enhanced search state
  const [searchMode, setSearchMode] = useState('phone'); // 'phone', 'name', 'advanced'
  const [searchResults, setSearchResults] = useState([]);
  const [searchMetadata, setSearchMetadata] = useState(null);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [searchFilters, setSearchFilters] = useState({
    search_term: '',
    min_age: '',
    max_age: '',
    gender: 'any',
    blood_group: 'any',
    has_recent_appointments: null,
    sort_by: 'name',
    sort_order: 'asc'
  });
  const [showPatientDialog, setShowPatientDialog] = useState(false);
  const [showAppointmentDialog, setShowAppointmentDialog] = useState(false);

  // Patient form state
  const [patientForm, setPatientForm] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
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

  // Appointment form state
  const [appointmentForm, setAppointmentForm] = useState({
    patient_id: '',
    doctor_id: '',
    appointment_date: '',
    appointment_time: '',
    duration_minutes: 30,
    appointment_type: 'consultation',
    reason: '',
    priority: 'normal',
    notes: '',
    payment_status: 'pending',
    payment_method: '',
    discount_amount: 0,
    payment_notes: ''
  });

  const [loading, setLoading] = useState(false);

  // Fetch initial data
  useEffect(() => {
    fetchDoctors();
    fetchTodayAppointments();
  }, []);

  const fetchDoctors = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/doctors', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setDoctors(data);
      } else {
        console.error('Failed to fetch doctors:', response.status);
      }
    } catch (error) {
      console.error('Error fetching doctors:', error);
    }
  };

  const fetchTodayAppointments = async () => {
    try {
      const token = localStorage.getItem('token');
      const today = format(new Date(), 'yyyy-MM-dd');
      const response = await fetch(`/api/appointments/?date_from=${today}&date_to=${today}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setAppointments(data);
      } else {
        console.error('Failed to fetch appointments:', response.status);
      }
    } catch (error) {
      console.error('Error fetching appointments:', error);
    }
  };

  const searchPatientByPhone = async () => {
    if (!searchPhone) return;
    
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/patients/phone/${searchPhone}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const patient = await response.json();
        setSelectedPatient(patient);
        if (patient) {
          setAppointmentForm(prev => ({ ...prev, patient_id: patient.patient_id }));
        }
      } else if (response.status === 404 || response.status === 401) {
        setSelectedPatient(null);
        setPatientForm(prev => ({ ...prev, primary_phone: searchPhone }));
        setShowPatientDialog(true);
      } else {
        console.error('Error searching patient:', response.status);
        toast({ variant: 'destructive', title: 'Error', description: 'Error searching patient. Please try again.' });
      }
    } catch (error) {
      console.error('Error searching patient:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error searching patient. Please check your connection.' });
    }
    setLoading(false);
  };

  const searchPatientsAdvanced = async (page = 1) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const searchPayload = {
        ...searchFilters,
        min_age: searchFilters.min_age ? parseInt(searchFilters.min_age) : null,
        max_age: searchFilters.max_age ? parseInt(searchFilters.max_age) : null,
        gender: searchFilters.gender === 'any' ? '' : searchFilters.gender,
        blood_group: searchFilters.blood_group === 'any' ? '' : searchFilters.blood_group,
      };

      const response = await fetch(`/api/patients/search?page=${page}&per_page=10`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(searchPayload)
      });

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.patients);
        setSearchMetadata(data.metadata);
        setShowSearchResults(true);
        setSelectedPatient(null);
      } else {
        console.error('Error searching patients:', response.status);
        toast({ variant: 'destructive', title: 'Error', description: 'Error searching patients. Please try again.' });
      }
    } catch (error) {
      console.error('Error searching patients:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error searching patients. Please check your connection.' });
    }
    setLoading(false);
  };

  const selectPatientFromSearch = (patient) => {
    setSelectedPatient(patient);
    setAppointmentForm(prev => ({
      ...prev,
      patient_id: patient.patient_id
    }));
    setShowSearchResults(false);
  };

  const getAgeDisplay = (dateOfBirth, age) => {
    if (age !== null && age !== undefined) {
      return `${age} years`;
    }
    if (dateOfBirth) {
      const today = new Date();
      const birthDate = new Date(dateOfBirth);
      const calculatedAge = Math.floor((today - birthDate) / (365.25 * 24 * 60 * 60 * 1000));
      return `${calculatedAge} years`;
    }
    return 'N/A';
  };

  const getVisitStatusBadge = (status) => {
    const statusColors = {
      recent: 'bg-green-100 text-green-800',
      moderate: 'bg-yellow-100 text-yellow-800',
      old: 'bg-red-100 text-red-800'
    };
    const statusLabels = {
      recent: 'Recent Visit',
      moderate: 'Regular Patient',
      old: 'Long Gap'
    };
    
    if (!status) return null;
    
    return (
      <Badge className={statusColors[status]}>
        {statusLabels[status]}
      </Badge>
    );
  };

  const createPatient = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/patients/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(patientForm)
      });
      
      if (response.ok) {
        const newPatient = await response.json();
        setSelectedPatient(newPatient);
        setAppointmentForm(prev => ({ ...prev, patient_id: newPatient.patient_id }));
        setShowPatientDialog(false);
        // Reset form
        setPatientForm({
          first_name: '',
          last_name: '',
          date_of_birth: '',
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
      } else {
        const error = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: `Error creating patient: ${error.detail}` });
      }
    } catch (error) {
      console.error('Error creating patient:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error creating patient' });
    }
    setLoading(false);
  };

  const createAppointment = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/appointments/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(appointmentForm)
      });
      
      if (response.ok) {
        const newAppointment = await response.json();
        setAppointments(prev => [...prev, newAppointment]);
        setShowAppointmentDialog(false);
        // Reset form
        setAppointmentForm({
          patient_id: '',
          doctor_id: '',
          appointment_date: '',
          appointment_time: '',
          duration_minutes: 30,
          appointment_type: 'consultation',
          reason: '',
          priority: 'normal',
          notes: '',
          payment_status: 'pending',
          payment_method: '',
          discount_amount: 0,
          payment_notes: ''
        });
        setSelectedPatient(null);
        setSearchPhone('');
        toast({ title: 'Success', description: 'Appointment created successfully!' });
      } else {
        const error = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: `Error creating appointment: ${error.detail}` });
      }
    } catch (error) {
      console.error('Error creating appointment:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error creating appointment' });
    }
    setLoading(false);
  };

  const getStatusColor = (status) => {
    const colors = {
      scheduled: 'bg-blue-100 text-blue-800',
      confirmed: 'bg-green-100 text-green-800',
      in_progress: 'bg-yellow-100 text-yellow-800',
      completed: 'bg-gray-100 text-gray-800',
      cancelled: 'bg-red-100 text-red-800',
      no_show: 'bg-red-100 text-red-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getPriorityColor = (priority) => {
    const colors = {
      normal: 'bg-blue-100 text-blue-800',
      urgent: 'bg-orange-100 text-orange-800',
      emergency: 'bg-red-100 text-red-800'
    };
    return colors[priority] || 'bg-gray-100 text-gray-800';
  };

  const deleteAppointment = async (appointmentId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/${appointmentId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        setAppointments(prev => prev.filter(apt => apt.id !== appointmentId));
        toast({ title: 'Success', description: 'Appointment deleted successfully!' });
      } else {
        const errorData = await response.json();
        toast({ variant: 'destructive', title: 'Error', description: `Error deleting appointment: ${errorData.detail}` });
      }
    } catch (error) {
      console.error('Error deleting appointment:', error);
      toast({ variant: 'destructive', title: 'Error', description: 'Error deleting appointment' });
    }
  };

  const handleDeleteClick = (appointmentId) => {
    setConfirmState({
      open: true,
      message: 'Are you sure you want to delete this appointment?',
      onConfirm: () => {
        setConfirmState({ open: false });
        deleteAppointment(appointmentId);
      }
    });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900">Outpatient Management</h1>
      
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="reception">Reception Desk</TabsTrigger>
          <TabsTrigger value="appointments">Today's Appointments</TabsTrigger>
        </TabsList>

        {/* Reception Tab */}
        <TabsContent value="reception" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Patient Registration & Appointment Booking
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Enhanced Patient Search */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label className="text-lg font-semibold">Find Patient</Label>
                  <Tabs value={searchMode} onValueChange={setSearchMode} className="w-auto">
                    <TabsList className="grid grid-cols-3 w-[400px]">
                      <TabsTrigger value="phone">By Phone</TabsTrigger>
                      <TabsTrigger value="name">By Name</TabsTrigger>
                      <TabsTrigger value="advanced">Advanced</TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                {/* Phone Search */}
                {searchMode === 'phone' && (
                  <div className="flex gap-2">
                    <Input
                      placeholder="Enter phone number"
                      value={searchPhone}
                      onChange={(e) => setSearchPhone(e.target.value)}
                      className="flex-1"
                    />
                    <Button onClick={searchPatientByPhone} disabled={loading}>
                      <Search className="h-4 w-4 mr-2" />
                      Search
                    </Button>
                  </div>
                )}

                {/* Name Search */}
                {searchMode === 'name' && (
                  <div className="flex gap-2">
                    <Input
                      placeholder="Enter patient name"
                      value={searchFilters.search_term}
                      onChange={(e) => setSearchFilters(prev => ({ ...prev, search_term: e.target.value }))}
                      className="flex-1"
                    />
                    <Button onClick={() => searchPatientsAdvanced(1)} disabled={loading}>
                      <Search className="h-4 w-4 mr-2" />
                      Search
                    </Button>
                  </div>
                )}

                {/* Advanced Search */}
                {searchMode === 'advanced' && (
                  <div className="space-y-3 p-4 border rounded-lg bg-gray-50">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      <div>
                        <Label htmlFor="name-search">Name/Phone/ID</Label>
                        <Input
                          id="name-search"
                          placeholder="Search term"
                          value={searchFilters.search_term}
                          onChange={(e) => setSearchFilters(prev => ({ ...prev, search_term: e.target.value }))}
                        />
                      </div>
                      <div>
                        <Label htmlFor="min-age">Min Age</Label>
                        <Input
                          id="min-age"
                          type="number"
                          placeholder="Min age"
                          value={searchFilters.min_age}
                          onChange={(e) => setSearchFilters(prev => ({ ...prev, min_age: e.target.value }))}
                        />
                      </div>
                      <div>
                        <Label htmlFor="max-age">Max Age</Label>
                        <Input
                          id="max-age"
                          type="number"
                          placeholder="Max age"
                          value={searchFilters.max_age}
                          onChange={(e) => setSearchFilters(prev => ({ ...prev, max_age: e.target.value }))}
                        />
                      </div>
                      <div>
                        <Label htmlFor="gender">Gender</Label>
                        <Select value={searchFilters.gender} onValueChange={(value) => setSearchFilters(prev => ({ ...prev, gender: value }))}>
                          <SelectTrigger>
                            <SelectValue placeholder="Any" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
                            <SelectItem value="Male">Male</SelectItem>
                            <SelectItem value="Female">Female</SelectItem>
                            <SelectItem value="Other">Other</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor="blood-group">Blood Group</Label>
                        <Select value={searchFilters.blood_group} onValueChange={(value) => setSearchFilters(prev => ({ ...prev, blood_group: value }))}>
                          <SelectTrigger>
                            <SelectValue placeholder="Any" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any</SelectItem>
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
                        <Label htmlFor="sort-by">Sort By</Label>
                        <Select value={searchFilters.sort_by} onValueChange={(value) => setSearchFilters(prev => ({ ...prev, sort_by: value }))}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="name">Name</SelectItem>
                            <SelectItem value="age">Age</SelectItem>
                            <SelectItem value="last_visit">Last Visit</SelectItem>
                            <SelectItem value="created_at">Registration Date</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                      <Button onClick={() => searchPatientsAdvanced(1)} disabled={loading} className="flex-1">
                        <Search className="h-4 w-4 mr-2" />
                        Search Patients
                      </Button>
                      <Button 
                        variant="outline" 
                        onClick={() => {
                          setSearchFilters({
                            search_term: '',
                            min_age: '',
                            max_age: '',
                            gender: '',
                            blood_group: '',
                            has_recent_appointments: null,
                            sort_by: 'name',
                            sort_order: 'asc'
                          });
                          setSearchResults([]);
                          setShowSearchResults(false);
                        }}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Selected Patient Display */}
              {selectedPatient && (
                <Card className="bg-green-50 border-green-200">
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-semibold text-lg">
                          {selectedPatient.first_name} {selectedPatient.last_name}
                        </h3>
                        <p className="text-sm text-gray-600">Patient ID: {selectedPatient.patient_id}</p>
                        <p className="text-sm text-gray-600">Phone: {selectedPatient.primary_phone}</p>
                        {selectedPatient.date_of_birth && (
                          <p className="text-sm text-gray-600">
                            DOB: {format(new Date(selectedPatient.date_of_birth), 'dd/MM/yyyy')}
                          </p>
                        )}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowAppointmentDialog(true)}
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        Book Appointment
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Search Results */}
              {showSearchResults && searchResults.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span>Search Results ({searchMetadata?.total_count || 0} patients found)</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowSearchResults(false)}
                      >
                        ✕
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {searchResults.map((patient) => (
                      <Card key={patient.id} className="border-l-4 border-l-blue-500">
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
                                {getVisitStatusBadge(patient.recent_visit_status)}
                              </div>
                              <div className="text-sm text-gray-600 space-y-1">
                                <p>📱 {patient.primary_phone}</p>
                                <p>🆔 {patient.patient_id}</p>
                                <div className="flex items-center gap-4">
                                  <span>👤 {getAgeDisplay(patient.date_of_birth, patient.age)}</span>
                                  <span>📅 {patient.total_appointments} visits</span>
                                  {patient.last_appointment_date && (
                                    <span>
                                      🏥 Last: {format(new Date(patient.last_appointment_date), 'dd/MM/yyyy')}
                                    </span>
                                  )}
                                </div>
                                {patient.address && (
                                  <p className="text-xs">📍 {patient.address}</p>
                                )}
                              </div>
                            </div>
                            <div className="flex flex-col gap-2">
                              <Button
                                size="sm"
                                onClick={() => selectPatientFromSearch(patient)}
                                className="w-full"
                              >
                                Select
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  selectPatientFromSearch(patient);
                                  setShowAppointmentDialog(true);
                                }}
                              >
                                <Plus className="h-4 w-4 mr-1" />
                                Book
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                    
                    {/* Pagination */}
                    {searchMetadata && searchMetadata.total_pages > 1 && (
                      <div className="flex items-center justify-between pt-4">
                        <p className="text-sm text-gray-600">
                          Page {searchMetadata.page} of {searchMetadata.total_pages} 
                          ({searchMetadata.per_page} per page)
                        </p>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={searchMetadata.page === 1}
                            onClick={() => searchPatientsAdvanced(searchMetadata.page - 1)}
                          >
                            Previous
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={searchMetadata.page === searchMetadata.total_pages}
                            onClick={() => searchPatientsAdvanced(searchMetadata.page + 1)}
                          >
                            Next
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Empty Search Results */}
              {showSearchResults && searchResults.length === 0 && (
                <Card className="border-yellow-200 bg-yellow-50">
                  <CardContent className="pt-4 text-center">
                    <p className="text-yellow-800">No patients found matching your search criteria.</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      onClick={() => setShowSearchResults(false)}
                    >
                      Clear Search
                    </Button>
                  </CardContent>
                </Card>
              )}

              {/* Quick Actions */}
              <div className="flex gap-2">
                <Dialog open={showPatientDialog} onOpenChange={setShowPatientDialog}>
                  <DialogTrigger asChild>
                    <Button variant="outline">
                      <Plus className="h-4 w-4 mr-2" />
                      Register New Patient
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                      <DialogTitle>Register New Patient</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={createPatient} className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="first_name">First Name *</Label>
                          <Input
                            id="first_name"
                            required
                            value={patientForm.first_name}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, first_name: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="last_name">Last Name *</Label>
                          <Input
                            id="last_name"
                            required
                            value={patientForm.last_name}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, last_name: e.target.value }))}
                          />
                        </div>
                      </div>
                      <div>
                        <Label htmlFor="primary_phone">Phone Number *</Label>
                        <Input
                          id="primary_phone"
                          required
                          value={patientForm.primary_phone}
                          onChange={(e) => setPatientForm(prev => ({ ...prev, primary_phone: e.target.value }))}
                        />
                      </div>
                      <div>
                        <Label htmlFor="date_of_birth">Date of Birth</Label>
                        <Input
                          id="date_of_birth"
                          type="date"
                          value={patientForm.date_of_birth}
                          onChange={(e) => setPatientForm(prev => ({ ...prev, date_of_birth: e.target.value }))}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="gender">Gender</Label>
                          <Select
                            value={patientForm.gender}
                            onValueChange={(value) => setPatientForm(prev => ({ ...prev, gender: value }))}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select gender" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="male">Male</SelectItem>
                              <SelectItem value="female">Female</SelectItem>
                              <SelectItem value="other">Other</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label htmlFor="blood_group">Blood Group</Label>
                          <Select
                            value={patientForm.blood_group}
                            onValueChange={(value) => setPatientForm(prev => ({ ...prev, blood_group: value }))}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select blood group" />
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
                          <Label htmlFor="marital_status">Marital Status</Label>
                          <Select
                            value={patientForm.marital_status}
                            onValueChange={(value) => setPatientForm(prev => ({ ...prev, marital_status: value }))}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select marital status" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="Single">Single</SelectItem>
                              <SelectItem value="Married">Married</SelectItem>
                              <SelectItem value="Widowed">Widowed</SelectItem>
                              <SelectItem value="Divorced">Divorced</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label htmlFor="abha_id">ABHA ID</Label>
                          <Input
                            id="abha_id"
                            placeholder="14-digit ABHA number"
                            value={patientForm.abha_id}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, abha_id: e.target.value }))}
                          />
                        </div>
                      </div>
                      <div>
                        <Label htmlFor="email">Email</Label>
                        <Input
                          id="email"
                          type="email"
                          value={patientForm.email}
                          onChange={(e) => setPatientForm(prev => ({ ...prev, email: e.target.value }))}
                        />
                      </div>

                      {/* Emergency Contact */}
                      <div className="col-span-2 border-t pt-4">
                        <h4 className="font-medium text-sm mb-3">Emergency Contact</h4>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="emergency_contact_name">Contact Name</Label>
                          <Input
                            id="emergency_contact_name"
                            value={patientForm.emergency_contact_name}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, emergency_contact_name: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="emergency_contact_phone">Contact Phone</Label>
                          <Input
                            id="emergency_contact_phone"
                            value={patientForm.emergency_contact_phone}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, emergency_contact_phone: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="emergency_contact_relation">Relation</Label>
                          <Select
                            value={patientForm.emergency_contact_relation}
                            onValueChange={(value) => setPatientForm(prev => ({ ...prev, emergency_contact_relation: value }))}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select relation" />
                            </SelectTrigger>
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
                      </div>

                      {/* Address */}
                      <div className="col-span-2 border-t pt-4">
                        <h4 className="font-medium text-sm mb-3">Address</h4>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="col-span-2">
                          <Label htmlFor="address_line1">Address Line 1</Label>
                          <Input
                            id="address_line1"
                            value={patientForm.address_line1}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, address_line1: e.target.value }))}
                          />
                        </div>
                        <div className="col-span-2">
                          <Label htmlFor="address_line2">Address Line 2</Label>
                          <Input
                            id="address_line2"
                            value={patientForm.address_line2}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, address_line2: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="village">Village/Town</Label>
                          <Input
                            id="village"
                            value={patientForm.village}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, village: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="mandal">Mandal/Taluka</Label>
                          <Input
                            id="mandal"
                            value={patientForm.mandal}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, mandal: e.target.value }))}
                          />
                        </div>
                        <div>
                          <Label htmlFor="district">District</Label>
                          <Input
                            id="district"
                            value={patientForm.district}
                            onChange={(e) => setPatientForm(prev => ({ ...prev, district: e.target.value }))}
                          />
                        </div>
                      </div>
                      <Button type="submit" disabled={loading} className="w-full">
                        {loading ? 'Creating...' : 'Create Patient'}
                      </Button>
                    </form>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>

          {/* Appointment Booking Dialog */}
          <Dialog open={showAppointmentDialog} onOpenChange={setShowAppointmentDialog}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Book Appointment</DialogTitle>
              </DialogHeader>
              <form onSubmit={createAppointment} className="space-y-4">
                <div>
                  <Label htmlFor="doctor_id">Doctor *</Label>
                  <Select
                    required
                    value={appointmentForm.doctor_id}
                    onValueChange={(value) => setAppointmentForm(prev => ({ ...prev, doctor_id: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select doctor" />
                    </SelectTrigger>
                    <SelectContent>
                      {doctors.map((doctor) => (
                        <SelectItem key={doctor.id} value={doctor.id.toString()}>
                          Dr. {doctor.first_name} {doctor.last_name} - {doctor.specialization}
                          {doctor.consultation_fee_inr && (
                            <span className="text-sm text-green-600 ml-2">
                              (Fee: {doctor.consultation_fee_inr})
                            </span>
                          )}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                {/* Consultation Fee Display */}
                {appointmentForm.doctor_id && (
                  <div className="bg-green-50 border border-green-200 rounded-md p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-green-800">
                        Consultation Fee:
                      </span>
                      <span className="text-lg font-bold text-green-900">
                        {doctors.find(d => d.id.toString() === appointmentForm.doctor_id)?.consultation_fee_inr || 'N/A'}
                      </span>
                    </div>
                  </div>
                )}

                {/* Payment Status */}
                <div>
                  <Label htmlFor="payment_status">Payment Status</Label>
                  <Select
                    value={appointmentForm.payment_status || 'pending'}
                    onValueChange={(value) => setAppointmentForm(prev => ({ ...prev, payment_status: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select payment status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="paid">Paid</SelectItem>
                      <SelectItem value="partial">Partial</SelectItem>
                      <SelectItem value="waived">Waived</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Payment Method (if paid or partial) */}
                {appointmentForm.payment_status === 'paid' || appointmentForm.payment_status === 'partial' ? (
                  <div>
                    <Label htmlFor="payment_method">Payment Method</Label>
                    <Select
                      value={appointmentForm.payment_method || ''}
                      onValueChange={(value) => setAppointmentForm(prev => ({ ...prev, payment_method: value }))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select payment method" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cash">Cash</SelectItem>
                        <SelectItem value="card">Card</SelectItem>
                        <SelectItem value="insurance">Insurance</SelectItem>
                        <SelectItem value="online">Online</SelectItem>
                        <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}

                {/* Discount Amount */}
                <div>
                  <Label htmlFor="discount_amount">Discount Amount (₹)</Label>
                  <Input
                    id="discount_amount"
                    type="number"
                    min="0"
                    step="0.01"
                    value={appointmentForm.discount_amount}
                    onChange={(e) => setAppointmentForm(prev => ({ ...prev, discount_amount: parseFloat(e.target.value) || 0 }))}
                    placeholder="0.00"
                  />
                </div>

                {/* Payment Notes */}
                <div>
                  <Label htmlFor="payment_notes">Payment Notes</Label>
                  <textarea
                    id="payment_notes"
                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    value={appointmentForm.payment_notes}
                    onChange={(e) => setAppointmentForm(prev => ({ ...prev, payment_notes: e.target.value }))}
                    placeholder="Payment notes or comments..."
                  />
                </div>

                <div>
                  <Label htmlFor="appointment_date">Date *</Label>
                  <Input
                    id="appointment_date"
                    type="date"
                    required
                    value={appointmentForm.appointment_date}
                    onChange={(e) => setAppointmentForm(prev => ({ ...prev, appointment_date: e.target.value }))}
                    min={format(new Date(), 'yyyy-MM-dd')}
                  />
                </div>
                <div>
                  <Label htmlFor="appointment_time">Time *</Label>
                  <Input
                    id="appointment_time"
                    type="time"
                    required
                    value={appointmentForm.appointment_time}
                    onChange={(e) => setAppointmentForm(prev => ({ ...prev, appointment_time: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="appointment_type">Type</Label>
                    <Select
                      value={appointmentForm.appointment_type}
                      onValueChange={(value) => setAppointmentForm(prev => ({ ...prev, appointment_type: value }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="consultation">Consultation</SelectItem>
                        <SelectItem value="followup">Follow-up</SelectItem>
                        <SelectItem value="checkup">Check-up</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="priority">Priority</Label>
                    <Select
                      value={appointmentForm.priority}
                      onValueChange={(value) => setAppointmentForm(prev => ({ ...prev, priority: value }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="normal">Normal</SelectItem>
                        <SelectItem value="urgent">Urgent</SelectItem>
                        <SelectItem value="emergency">Emergency</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label htmlFor="reason">Reason for Visit</Label>
                  <Textarea
                    id="reason"
                    value={appointmentForm.reason}
                    onChange={(e) => setAppointmentForm(prev => ({ ...prev, reason: e.target.value }))}
                    placeholder="Brief description of the visit reason"
                  />
                </div>
                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? 'Booking...' : 'Book Appointment'}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </TabsContent>

        {/* Appointments Tab */}
        <TabsContent value="appointments" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarIcon className="h-5 w-5" />
                Today's Appointments ({format(new Date(), 'dd/MM/yyyy')})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {appointments.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">No appointments scheduled for today</p>
                ) : (
                  appointments.map((appointment) => (
                    <Card key={appointment.id} className="border-l-4 border-l-blue-500">
                      <CardContent className="pt-4">
                        <div className="flex justify-between items-start">
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <h3 className="font-semibold">{appointment.patient_name}</h3>
                              <Badge className={getPriorityColor(appointment.priority)}>
                                {appointment.priority}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-4 text-sm text-gray-600">
                              <span className="flex items-center gap-1">
                                <Clock className="h-4 w-4" />
                                {appointment.appointment_time}
                              </span>
                              <span className="flex items-center gap-1">
                                <User className="h-4 w-4" />
                                {appointment.doctor_name}
                              </span>
                            </div>
                            <p className="text-sm text-gray-600">
                              Type: {appointment.appointment_type}
                              {appointment.reason && ` • ${appointment.reason}`}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <div className="flex items-center gap-2">
                              <Badge className={getStatusColor(appointment.status)}>
                                {appointment.status}
                              </Badge>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteClick(appointment.id)}
                                className="h-8 w-8 p-0 text-red-600 hover:text-red-800 hover:bg-red-50"
                                title="Delete appointment"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                            <span className="text-xs text-gray-500">
                              #{appointment.appointment_number}
                            </span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
      <ConfirmDialog
        open={confirmState.open}
        title="Delete Appointment"
        message={confirmState.message}
        confirmLabel="Delete"
        onConfirm={confirmState.onConfirm}
        onCancel={() => setConfirmState({ open: false })}
      />
    </div>
  );
};

export default OutpatientModule;
