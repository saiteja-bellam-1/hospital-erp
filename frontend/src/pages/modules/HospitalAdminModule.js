import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../hooks/use-toast';
import {
  Building2,
  Users,
  Settings,
  UserCheck,
  Save,
  Plus,
  Edit,
  Trash2,
  X,
  Receipt
} from 'lucide-react';
import axios from 'axios';
import ModuleConfigForm from './ModuleConfigForm';

const HospitalAdminModule = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('hospital-info');
  const [loading, setLoading] = useState(false);

  // Hospital Info State
  const [hospitalInfo, setHospitalInfo] = useState({
    name: '',
    address: '',
    city: '',
    state: '',
    postal_code: '',
    country: '',
    phone: '',
    fax: '',
    email: '',
    website: '',
    license_number: '',
    registration_number: '',
    tax_id: '',
    logo_url: '',
    description: ''
  });

  // Doctors State
  const [doctors, setDoctors] = useState([]);
  const [showDoctorProfile, setShowDoctorProfile] = useState(false);
  const [editingDoctor, setEditingDoctor] = useState(null);
  const [doctorProfile, setDoctorProfile] = useState({
    consultation_fee: '',
    specialization: '',
    qualification: '',
    experience_years: ''
  });

  // Registration Fee State
  const [registrationFee, setRegistrationFee] = useState(0);

  // Module Settings State
  const [selectedModule, setSelectedModule] = useState('lab');
  const [moduleSettings, setModuleSettings] = useState([]);
  const [showSettingForm, setShowSettingForm] = useState(false);
  const [settingForm, setSettingForm] = useState({
    setting_key: '',
    setting_value: '',
    setting_type: 'string',
    description: ''
  });

  const modules = [
    { id: 'lab', name: 'Laboratory', description: 'Lab tests and reports' },
    { id: 'pharmacy', name: 'Pharmacy', description: 'Medication management' },
    { id: 'billing', name: 'Billing', description: 'Financial operations' },
    { id: 'outpatient', name: 'Outpatient', description: 'OPD management' },
    { id: 'inpatient', name: 'Inpatient', description: 'IPD management' }
  ];

  useEffect(() => {
    if (user?.role === 'super_admin' || user?.role === 'hospital_admin') {
      fetchHospitalInfo();
      fetchDoctors();
      fetchRegistrationFee();
      if (selectedModule) {
        fetchModuleSettings(selectedModule);
      }
    }
  }, [user, selectedModule]);

  const fetchHospitalInfo = async () => {
    try {
      const response = await axios.get('/api/hospital/info');
      setHospitalInfo(response.data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to fetch hospital information"
      });
    }
  };

  const fetchDoctors = async () => {
    try {
      const response = await axios.get('/api/hospital/doctors');
      setDoctors(response.data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to fetch doctors"
      });
    }
  };

  const fetchModuleSettings = async (moduleName) => {
    try {
      const response = await axios.get(`/api/hospital/module-settings/${moduleName}`);
      setModuleSettings(response.data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to fetch module settings"
      });
    }
  };

  const fetchRegistrationFee = async () => {
    try {
      const response = await axios.get('/api/hospital/registration-fee');
      setRegistrationFee(response.data.registration_fee || 0);
    } catch (error) {
      console.error('Failed to fetch registration fee:', error);
    }
  };

  const saveRegistrationFee = async () => {
    setLoading(true);
    try {
      await axios.put('/api/hospital/registration-fee', { registration_fee: parseFloat(registrationFee) || 0 });
      toast({ title: 'Success', description: 'Registration fee updated successfully' });
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update registration fee' });
    } finally {
      setLoading(false);
    }
  };

  const handleHospitalInfoSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.put('/api/hospital/info', hospitalInfo);
      toast({
        title: "Success",
        description: "Hospital information updated successfully"
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to update hospital information"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDoctorProfileSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.put(`/api/hospital/doctors/${editingDoctor.id}/profile`, doctorProfile);
      
      toast({
        title: "Success",
        description: "Doctor profile updated successfully"
      });
      
      setShowDoctorProfile(false);
      setEditingDoctor(null);
      setDoctorProfile({
        consultation_fee: '',
        specialization: '',
        qualification: '',
        experience_years: ''
      });
      fetchDoctors();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to update doctor profile"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleModuleSettingSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await axios.post(`/api/hospital/module-settings/${selectedModule}`, settingForm);
      
      toast({
        title: "Success",
        description: "Module setting saved successfully"
      });
      
      setShowSettingForm(false);
      setSettingForm({
        setting_key: '',
        setting_value: '',
        setting_type: 'string',
        description: ''
      });
      fetchModuleSettings(selectedModule);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to save module setting"
      });
    } finally {
      setLoading(false);
    }
  };

  const editDoctorProfile = (doctor) => {
    setEditingDoctor(doctor);
    setDoctorProfile({
      consultation_fee: doctor.consultation_fee || '',
      specialization: doctor.specialization || '',
      qualification: doctor.qualification || '',
      experience_years: doctor.experience_years || ''
    });
    setShowDoctorProfile(true);
  };

  if (user?.role !== 'super_admin' && user?.role !== 'hospital_admin') {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Access denied. Hospital admin privileges required.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Hospital Administration</h1>
      </div>

      {/* Navigation Tabs */}
      <div className="flex space-x-1 border-b">
        <Button
          variant="ghost"
          className={`px-4 py-2 ${
            activeTab === 'hospital-info'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-600 hover:text-gray-800'
          }`}
          onClick={() => setActiveTab('hospital-info')}
        >
          <Building2 className="h-4 w-4 mr-2" />
          Hospital Info
        </Button>
        <Button
          variant="ghost"
          className={`px-4 py-2 ${
            activeTab === 'doctors'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-600 hover:text-gray-800'
          }`}
          onClick={() => setActiveTab('doctors')}
        >
          <UserCheck className="h-4 w-4 mr-2" />
          Doctor Profiles
        </Button>
        <Button
          variant="ghost"
          className={`px-4 py-2 ${
            activeTab === 'module-settings'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-600 hover:text-gray-800'
          }`}
          onClick={() => setActiveTab('module-settings')}
        >
          <Settings className="h-4 w-4 mr-2" />
          Module Settings
        </Button>
        <Button
          variant="ghost"
          className={`px-4 py-2 ${
            activeTab === 'billing-settings'
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-gray-600 hover:text-gray-800'
          }`}
          onClick={() => setActiveTab('billing-settings')}
        >
          <Receipt className="h-4 w-4 mr-2" />
          Billing Settings
        </Button>
      </div>

      {/* Hospital Information Tab */}
      {activeTab === 'hospital-info' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Building2 className="h-5 w-5 mr-2" />
              Hospital Information
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleHospitalInfoSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="name">Hospital Name</Label>
                  <Input
                    id="name"
                    value={hospitalInfo.name}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, name: e.target.value })}
                    placeholder="Enter hospital name"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={hospitalInfo.email}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, email: e.target.value })}
                    placeholder="hospital@example.com"
                  />
                </div>
                <div>
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    value={hospitalInfo.phone}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, phone: e.target.value })}
                    placeholder="+1-555-0123"
                  />
                </div>
                <div>
                  <Label htmlFor="fax">Fax</Label>
                  <Input
                    id="fax"
                    value={hospitalInfo.fax}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, fax: e.target.value })}
                    placeholder="+1-555-0124"
                  />
                </div>
                <div>
                  <Label htmlFor="website">Website</Label>
                  <Input
                    id="website"
                    value={hospitalInfo.website}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, website: e.target.value })}
                    placeholder="https://www.hospital.com"
                  />
                </div>
                <div>
                  <Label htmlFor="license_number">License Number</Label>
                  <Input
                    id="license_number"
                    value={hospitalInfo.license_number}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, license_number: e.target.value })}
                    placeholder="LIC-2024-001"
                  />
                </div>
                <div>
                  <Label htmlFor="registration_number">Registration Number</Label>
                  <Input
                    id="registration_number"
                    value={hospitalInfo.registration_number}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, registration_number: e.target.value })}
                    placeholder="REG-2024-001"
                  />
                </div>
                <div>
                  <Label htmlFor="tax_id">Tax ID</Label>
                  <Input
                    id="tax_id"
                    value={hospitalInfo.tax_id}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, tax_id: e.target.value })}
                    placeholder="TAX-123456789"
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="address">Address</Label>
                <Textarea
                  id="address"
                  value={hospitalInfo.address}
                  onChange={(e) => setHospitalInfo({ ...hospitalInfo, address: e.target.value })}
                  placeholder="Enter full address"
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    value={hospitalInfo.city}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, city: e.target.value })}
                    placeholder="City"
                  />
                </div>
                <div>
                  <Label htmlFor="state">State</Label>
                  <Input
                    id="state"
                    value={hospitalInfo.state}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, state: e.target.value })}
                    placeholder="State"
                  />
                </div>
                <div>
                  <Label htmlFor="postal_code">Postal Code</Label>
                  <Input
                    id="postal_code"
                    value={hospitalInfo.postal_code}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, postal_code: e.target.value })}
                    placeholder="12345"
                  />
                </div>
                <div>
                  <Label htmlFor="country">Country</Label>
                  <Input
                    id="country"
                    value={hospitalInfo.country}
                    onChange={(e) => setHospitalInfo({ ...hospitalInfo, country: e.target.value })}
                    placeholder="Country"
                  />
                </div>
              </div>

              <div>
                <Label>Hospital Logo</Label>
                <div className="mt-1 flex items-center gap-4">
                  {hospitalInfo.logo_url && (
                    <img src={hospitalInfo.logo_url} alt="Logo" className="h-16 w-16 object-contain border rounded" />
                  )}
                  <div>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      id="logo-upload"
                      className="hidden"
                      onChange={async (e) => {
                        const file = e.target.files[0];
                        if (!file) return;
                        if (file.size > 2 * 1024 * 1024) {
                          toast({ variant: 'destructive', title: 'Error', description: 'File size must be under 2MB' });
                          return;
                        }
                        const formData = new FormData();
                        formData.append('file', file);
                        try {
                          const res = await axios.post('/api/hospital/upload-file', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' }
                          });
                          setHospitalInfo({ ...hospitalInfo, logo_url: res.data.url });
                          toast({ title: 'Logo uploaded' });
                        } catch {
                          toast({ variant: 'destructive', title: 'Error', description: 'Failed to upload logo' });
                        }
                        e.target.value = '';
                      }}
                    />
                    <Button type="button" variant="outline" size="sm" onClick={() => document.getElementById('logo-upload').click()}>
                      {hospitalInfo.logo_url ? 'Change Logo' : 'Upload Logo'}
                    </Button>
                    {hospitalInfo.logo_url && (
                      <Button type="button" variant="ghost" size="sm" className="text-red-500 ml-1"
                        onClick={() => setHospitalInfo({ ...hospitalInfo, logo_url: '' })}>
                        Remove
                      </Button>
                    )}
                    <p className="text-[10px] text-gray-400 mt-1">PNG, JPEG, or WebP. Max 2MB.</p>
                  </div>
                </div>
              </div>

              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={hospitalInfo.description}
                  onChange={(e) => setHospitalInfo({ ...hospitalInfo, description: e.target.value })}
                  placeholder="Brief description of the hospital"
                  rows={3}
                />
              </div>

              <Button type="submit" disabled={loading}>
                <Save className="h-4 w-4 mr-2" />
                {loading ? 'Saving...' : 'Save Hospital Information'}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Doctor Profiles Tab */}
      {activeTab === 'doctors' && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <UserCheck className="h-5 w-5 mr-2" />
                Doctor Profiles
              </CardTitle>
            </CardHeader>
            <CardContent>
              {doctors.length === 0 ? (
                <p className="text-gray-500 text-center py-4">No doctors found. Create doctors from the Administration panel.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2">Name</th>
                        <th className="text-left py-2">Specialization</th>
                        <th className="text-left py-2">Qualification</th>
                        <th className="text-left py-2">Experience</th>
                        <th className="text-left py-2">Consultation Fee</th>
                        <th className="text-left py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {doctors.map((doctor) => (
                        <tr key={doctor.id} className="border-b">
                          <td className="py-2">
                            Dr. {doctor.first_name} {doctor.last_name}
                          </td>
                          <td className="py-2">{doctor.specialization || 'Not set'}</td>
                          <td className="py-2">{doctor.qualification || 'Not set'}</td>
                          <td className="py-2">{doctor.experience_years ? `${doctor.experience_years} years` : 'Not set'}</td>
                          <td className="py-2">{doctor.consultation_fee ? `$${doctor.consultation_fee}` : 'Not set'}</td>
                          <td className="py-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => editDoctorProfile(doctor)}
                            >
                              <Edit className="h-4 w-4" />
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

          {/* Doctor Profile Edit Modal */}
          {showDoctorProfile && editingDoctor && (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
              <div className="bg-white rounded-lg p-6 w-full max-w-md">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">
                    Edit Dr. {editingDoctor.first_name} {editingDoctor.last_name} Profile
                  </h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowDoctorProfile(false)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                
                <form onSubmit={handleDoctorProfileSubmit} className="space-y-4">
                  <div>
                    <Label htmlFor="consultation_fee">Consultation Fee ($)</Label>
                    <Input
                      id="consultation_fee"
                      type="number"
                      step="0.01"
                      value={doctorProfile.consultation_fee}
                      onChange={(e) => setDoctorProfile({ ...doctorProfile, consultation_fee: e.target.value })}
                      placeholder="150.00"
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="specialization">Specialization</Label>
                    <Input
                      id="specialization"
                      value={doctorProfile.specialization}
                      onChange={(e) => setDoctorProfile({ ...doctorProfile, specialization: e.target.value })}
                      placeholder="Cardiology"
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="qualification">Qualification</Label>
                    <Input
                      id="qualification"
                      value={doctorProfile.qualification}
                      onChange={(e) => setDoctorProfile({ ...doctorProfile, qualification: e.target.value })}
                      placeholder="MD, FACC"
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="experience_years">Years of Experience</Label>
                    <Input
                      id="experience_years"
                      type="number"
                      value={doctorProfile.experience_years}
                      onChange={(e) => setDoctorProfile({ ...doctorProfile, experience_years: e.target.value })}
                      placeholder="15"
                    />
                  </div>

                  <div className="flex space-x-2 pt-4">
                    <Button type="submit" disabled={loading}>
                      <Save className="h-4 w-4 mr-2" />
                      {loading ? 'Saving...' : 'Save Profile'}
                    </Button>
                    <Button type="button" variant="outline" onClick={() => setShowDoctorProfile(false)}>
                      Cancel
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Billing Settings Tab */}
      {activeTab === 'billing-settings' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Receipt className="h-5 w-5 mr-2" />
              Billing Settings
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="max-w-md">
              <Label htmlFor="registration_fee" className="text-base font-medium">
                Patient Registration Fee (₹)
              </Label>
              <p className="text-sm text-gray-500 mt-1 mb-3">
                One-time fee charged when a new patient registers. This fee is automatically added to the first appointment bill. Existing patients are not charged this fee.
              </p>
              <div className="flex items-center gap-3">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">₹</span>
                  <Input
                    id="registration_fee"
                    type="number"
                    min="0"
                    step="1"
                    value={registrationFee}
                    onChange={(e) => setRegistrationFee(e.target.value)}
                    className="pl-8"
                    placeholder="0"
                  />
                </div>
                <Button onClick={saveRegistrationFee} disabled={loading}>
                  <Save className="h-4 w-4 mr-2" />
                  Save
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Module Settings Tab */}
      {activeTab === 'module-settings' && (
        <div className="space-y-6">
          {/* Module Selector */}
          <div className="flex flex-wrap gap-2">
            {[
              { id: 'lab', name: 'Laboratory' },
              { id: 'pharmacy', name: 'Pharmacy' },
            ].map((module) => (
              <Button
                key={module.id}
                variant={selectedModule === module.id ? 'default' : 'outline'}
                onClick={() => setSelectedModule(module.id)}
              >
                {module.name}
              </Button>
            ))}
          </div>

          {/* Structured Config Form */}
          {(selectedModule === 'lab' || selectedModule === 'pharmacy') && (
            <ModuleConfigForm moduleName={selectedModule} />
          )}
        </div>
      )}
    </div>
  );
};

export default HospitalAdminModule;