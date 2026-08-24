import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../hooks/use-toast';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import {
  Plus,
  Edit,
  Trash2,
  Save,
  X,
  RefreshCw,
  KeyRound,
  Upload
} from 'lucide-react';
import axios from 'axios';
import BulkUserImportDialog from './admin/BulkUserImport';
import RolePermissionsEditor from './admin/RolePermissionsEditor';

const ADMIN_PAGE_TITLES = {
  users: 'Users',
  roles: 'Roles & Permissions',
};

const AdminModule = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const location = useLocation();
  const userRoles = user?.roles || [user?.role];
  const hasRole = (r) => userRoles.includes(r);
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [showUserForm, setShowUserForm] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [editingRole, setEditingRole] = useState(null);
  const [loading, setLoading] = useState(false);
  const [confirmState, setConfirmState] = useState({ open: false });
  const [passwordResetUser, setPasswordResetUser] = useState(null);
  const [newPassword, setNewPassword] = useState('');
  const [userLimit, setUserLimit] = useState(null);

  const [userForm, setUserForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    phone: '',
    role_id: '',
    role_ids: [],
    is_active: true,
    license_number: '',
    consultation_fee_inr: '',
    inpatient_fee_inr: '',
    inpatient_fee_charge_mode: 'per_day',
    emergency_fee_inr: '',
    specialization: '',
    qualification: '',
    experience_years: ''
  });

  const [roleForm, setRoleForm] = useState({
    name: '',
    description: ''
  });

  // Doctor room-type rate overrides
  const [doctorRoomRates, setDoctorRoomRates] = useState([]);
  const [doctorRoomRatesEdits, setDoctorRoomRatesEdits] = useState({});
  const [doctorRoomRatesSaving, setDoctorRoomRatesSaving] = useState({});

  const ROOM_TYPES = [
    { value: 'general',      label: 'General Ward' },
    { value: 'semi_private', label: 'Semi-Private' },
    { value: 'private',      label: 'Private' },
    { value: 'suite',        label: 'Suite / Deluxe' },
    { value: 'icu',          label: 'ICU' },
    { value: 'hdu',          label: 'HDU / Step-Down' },
    { value: 'nicu',         label: 'NICU' },
    { value: 'picu',         label: 'PICU' },
    { value: 'isolation',    label: 'Isolation' },
    { value: 'labour',       label: 'Labour & Delivery' },
    { value: 'recovery',     label: 'Post-Op Recovery' },
    { value: 'daycare',      label: 'Day Care' },
    { value: 'emergency',    label: 'Emergency / Casualty' },
    { value: 'operation',    label: 'Operation Theatre' },
  ];

  useEffect(() => {
    if (hasRole('super_admin') || hasRole('hospital_admin')) {
      fetchUsers(); fetchUserLimit();
      fetchRoles();
      fetchUserLimit();
    }
  }, [user]);

  const fetchUserLimit = async () => {
    try {
      const res = await axios.get('/api/admin/user-limit');
      setUserLimit(res.data);
    } catch {}
  };

  const fetchUsers = async () => {
    try {
      const response = await axios.get('/api/admin/users');
      setUsers(response.data);
    } catch (error) {
      toast({
        variant: "destructive", 
        title: "Error",
        description: "Failed to fetch users"
      });
    }
  };

  const fetchRoles = async () => {
    try {
      const response = await axios.get('/api/admin/roles');
      setRoles(response.data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error", 
        description: "Failed to fetch roles"
      });
    }
  };

  const handleUserSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const roleIds = (userForm.role_ids || []).length > 0 ? userForm.role_ids : [];
      if (roleIds.length === 0) {
        throw new Error('Please select at least one role');
      }

      const cleanedData = {
        ...userForm,
        role_id: roleIds[0],  // Primary role = first selected
        experience_years: userForm.experience_years ? parseInt(userForm.experience_years) : null,
        phone: userForm.phone || null,
        license_number: userForm.license_number || null,
        consultation_fee_inr: userForm.consultation_fee_inr || null,
        inpatient_fee_inr: userForm.inpatient_fee_inr || null,
        inpatient_fee_charge_mode: isDoctorRole()
          ? (userForm.inpatient_fee_charge_mode || 'per_day')
          : undefined,
        emergency_fee_inr: userForm.emergency_fee_inr || null,
        specialization: userForm.specialization || null,
        qualification: userForm.qualification || null,
      };
      delete cleanedData.role_ids;

      let userId;
      if (editingUser) {
        await axios.put(`/api/admin/users/${editingUser.id}`, cleanedData);
        userId = editingUser.id;
      } else {
        const response = await axios.post('/api/admin/users', cleanedData);
        userId = response.data.id;
      }

      // Assign multiple roles
      await axios.put(`/api/admin/users/${userId}/roles`, { role_ids: roleIds });

      fetchUsers(); fetchUserLimit();

      const isNewDoctor = !editingUser && roleIds.some(rid => {
        const r = roles.find(role => role.id === rid);
        return r?.name === 'doctor';
      });

      if (isNewDoctor) {
        // Keep dialog open in edit mode so the doctor can immediately set room-type rates
        const newUserRes = await axios.get(`/api/admin/users`);
        const newUser = (newUserRes.data || []).find(u => u.id === userId);
        if (newUser) {
          toast({ title: "User created", description: "Doctor saved — you can now set room-type visit rates below." });
          setEditingUser(newUser);
          try {
            const ratesRes = await axios.get('/api/inpatient/doctor-room-rates', { params: { doctor_id: userId } });
            const rates = ratesRes.data || [];
            setDoctorRoomRates(rates);
            const edits = {};
            rates.forEach(r => { edits[r.room_type] = String(r.visit_rate); });
            setDoctorRoomRatesEdits(edits);
          } catch { /* non-fatal */ }
          return; // keep dialog open
        }
      }

      toast({ title: "Success", description: editingUser ? "User updated successfully" : "User created successfully" });
      setShowUserForm(false);
      setEditingUser(null);
      setUserForm({
        username: '',
        email: '',
        password: '',
        first_name: '',
        last_name: '',
        phone: '',
        role_id: '',
        role_ids: [],
        is_active: true,
        license_number: '',
        consultation_fee_inr: '',
        inpatient_fee_inr: '',
        inpatient_fee_charge_mode: 'per_day',
        emergency_fee_inr: '',
        specialization: '',
        qualification: '',
        experience_years: ''
      });
    } catch (error) {
      console.error('Error creating/updating user:', error.response?.data || error);
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to save user"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRoleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (editingRole) {
        await axios.put(`/api/admin/roles/${editingRole.id}`, roleForm);
        toast({
          title: "Success",
          description: "Role updated successfully"
        });
      } else {
        await axios.post('/api/admin/roles', roleForm);
        toast({
          title: "Success",
          description: "Role created successfully"
        });
      }

      setShowRoleForm(false);
      setEditingRole(null);
      setRoleForm({ name: '', description: '' });
      fetchRoles();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error", 
        description: error.response?.data?.detail || "Failed to save role"
      });
    } finally {
      setLoading(false);
    }
  };

  const archiveUser = (userId, userName) => {
    setConfirmState({
      open: true,
      message: `Are you sure you want to archive "${userName}"? They will no longer be able to log in, but their data will be preserved.`,
      onConfirm: async () => {
        setConfirmState({ open: false });
        try {
          await axios.delete(`/api/admin/users/${userId}`);
          toast({
            title: "Success",
            description: "User archived successfully"
          });
          fetchUsers(); fetchUserLimit();
        } catch (error) {
          toast({
            variant: "destructive",
            title: "Error",
            description: error.response?.data?.detail || "Failed to archive user"
          });
        }
      }
    });
  };

  const restoreUser = async (userId) => {
    try {
      await axios.put(`/api/admin/users/${userId}/restore`);
      toast({
        title: "Success",
        description: "User restored successfully"
      });
      fetchUsers(); fetchUserLimit();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to restore user"
      });
    }
  };

  const handleResetPassword = async () => {
    if (!passwordResetUser || !newPassword || newPassword.length < 4) {
      toast({ variant: 'destructive', title: 'Error', description: 'Password must be at least 4 characters' });
      return;
    }
    try {
      await axios.put(`/api/admin/users/${passwordResetUser.id}/reset-password`, { new_password: newPassword });
      toast({ title: 'Success', description: `Password reset for ${passwordResetUser.username}` });
      setPasswordResetUser(null);
      setNewPassword('');
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: error.response?.data?.detail || 'Failed to reset password' });
    }
  };

  const deleteRole = (roleId) => {
    setConfirmState({
      open: true,
      message: 'Are you sure you want to delete this role?',
      onConfirm: async () => {
        setConfirmState({ open: false });
        try {
          await axios.delete(`/api/admin/roles/${roleId}`);
          toast({
            title: "Success",
            description: "Role deleted successfully"
          });
          fetchRoles();
        } catch (error) {
          toast({
            variant: "destructive",
            title: "Error",
            description: error.response?.data?.detail || "Failed to delete role"
          });
        }
      }
    });
  };

  const editUser = async (user) => {
    setEditingUser(user);
    const userRoleIds = (user.user_roles || []).map(r => r.id);
    setUserForm({
      username: user.username,
      email: user.email,
      password: '',
      first_name: user.first_name,
      last_name: user.last_name,
      phone: user.phone || '',
      role_id: user.user_role.id,
      role_ids: userRoleIds.length > 0 ? userRoleIds : [user.user_role.id],
      is_active: user.is_active,
      license_number: user.license_number || '',
      consultation_fee_inr: user.consultation_fee_inr || '',
      inpatient_fee_inr: user.inpatient_fee_inr || '',
      inpatient_fee_charge_mode: user.inpatient_fee_charge_mode || 'per_day',
      emergency_fee_inr: user.emergency_fee_inr || '',
      specialization: user.specialization || '',
      qualification: user.qualification || '',
      experience_years: user.experience_years || ''
    });
    // Load doctor room-type rates if this user has a doctor role
    const isDoctor = (user.user_roles || []).some(r => r.name === 'doctor') ||
                     user.user_role?.name === 'doctor';
    setDoctorRoomRates([]);
    setDoctorRoomRatesEdits({});
    if (isDoctor) {
      try {
        const res = await axios.get('/api/inpatient/doctor-room-rates', { params: { doctor_id: user.id } });
        const rates = res.data || [];
        setDoctorRoomRates(rates);
        const edits = {};
        rates.forEach(r => { edits[r.room_type] = String(r.visit_rate); });
        setDoctorRoomRatesEdits(edits);
      } catch { /* non-fatal */ }
    }
    setShowUserForm(true);
  };

  const editRole = (role) => {
    setEditingRole(role);
    setRoleForm({
      name: role.name,
      description: role.description || ''
    });
    setShowRoleForm(true);
  };

  const isDoctorRole = () => {
    return (userForm?.role_ids || []).some(rid => {
      const r = roles.find(role => role.id === rid);
      return r?.name === 'doctor';
    });
  };

  const isNurseRole = () => {
    return (userForm?.role_ids || []).some(rid => {
      const r = roles.find(role => role.id === rid);
      return r?.name === 'nurse';
    });
  };

  // Inpatient/visit fee is required for both doctors and nurses (same column on the user record).
  const requiresInpatientFee = () => isDoctorRole() || isNurseRole();

  if (!hasRole('super_admin') && !hasRole('hospital_admin')) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold text-gray-900">Access Denied</h1>
        <Card>
          <CardContent className="pt-6">
            <p className="text-gray-600">You do not have permission to access this page.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const defaultTab = 'users';
  const allowedTabs = ['users', 'roles'];
  const lastSegment = location.pathname.replace(/\/+$/, '').split('/').pop();
  if (lastSegment === 'admin' || !allowedTabs.includes(lastSegment)) {
    return <Navigate to={`/dashboard/admin/${defaultTab}`} replace />;
  }
  const activeTab = lastSegment;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">{ADMIN_PAGE_TITLES[activeTab]}</h1>
      </div>

      {/* User Management Tab */}
      {activeTab === 'users' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold">User Management</h2>
              {userLimit && !userLimit.unlimited && (
                <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                  userLimit.remaining === 0 ? 'bg-red-100 text-red-700' :
                  userLimit.remaining <= 2 ? 'bg-amber-100 text-amber-700' :
                  'bg-gray-100 text-gray-600'
                }`}>
                  {userLimit.active_users} / {userLimit.max_users} users
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {userLimit && !userLimit.unlimited && userLimit.remaining === 0 && (
                <p className="text-xs text-red-600">Limit reached. Upgrade license to add more.</p>
              )}
              <Button
                variant="outline"
                onClick={() => setShowBulkImport(true)}
                className="flex items-center"
                disabled={userLimit && !userLimit.unlimited && userLimit.remaining === 0}
                title="Import multiple doctors, nurses, or staff users from a CSV file"
              >
                <Upload className="h-4 w-4 mr-2" />
                Bulk Import
              </Button>
              <Button
                onClick={() => {
                  setShowUserForm(true);
                  setEditingUser(null);
                  setUserForm({
                    username: '',
                    email: '',
                    password: '',
                    first_name: '',
                    last_name: '',
                    phone: '',
                    role_id: '',
                    role_ids: [],
                    is_active: true,
                    license_number: '',
                    consultation_fee_inr: '',
                    inpatient_fee_inr: '',
                    inpatient_fee_charge_mode: 'per_day',
                    emergency_fee_inr: '',
                    specialization: '',
                    qualification: '',
                    experience_years: ''
                  });
                }}
                className="flex items-center"
                disabled={userLimit && !userLimit.unlimited && userLimit.remaining === 0}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add User
              </Button>
            </div>
          </div>

          <BulkUserImportDialog
            open={showBulkImport}
            onOpenChange={setShowBulkImport}
            onImported={() => { fetchUsers(); fetchUserLimit(); }}
          />

          {/* User Create/Edit Dialog */}
          <Dialog open={showUserForm} onOpenChange={(open) => { if (!open) { setShowUserForm(false); setEditingUser(null); } }}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editingUser ? 'Edit User' : 'Add New User'}</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleUserSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Username *</Label>
                    <Input value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} required />
                  </div>
                  <div>
                    <Label>Email *</Label>
                    <Input type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} required />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>First Name *</Label>
                    <Input value={userForm.first_name} onChange={(e) => setUserForm({ ...userForm, first_name: e.target.value })} required />
                  </div>
                  <div>
                    <Label>Last Name *</Label>
                    <Input value={userForm.last_name} onChange={(e) => setUserForm({ ...userForm, last_name: e.target.value })} required />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Phone</Label>
                    <Input value={userForm.phone} onChange={(e) => setUserForm({ ...userForm, phone: e.target.value })} />
                  </div>
                  {!editingUser && (
                    <div>
                      <Label>Password *</Label>
                      <Input type="password" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} required />
                    </div>
                  )}
                </div>

                {/* Roles */}
                <div>
                  <Label>Roles *</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {roles.filter(r => r.name !== 'super_admin').map((role) => {
                      const checked = (userForm.role_ids || []).includes(role.id);
                      return (
                        <label key={role.id}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm cursor-pointer border transition-colors ${
                            checked ? 'bg-blue-50 border-blue-300 text-blue-700' : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                          }`}>
                          <input type="checkbox" checked={checked}
                            onChange={(e) => {
                              const cur = userForm.role_ids || [];
                              const ids = e.target.checked ? [...cur, role.id] : cur.filter(id => id !== role.id);
                              setUserForm({ ...userForm, role_ids: ids, role_id: ids[0] || '' });
                            }}
                            className="w-3.5 h-3.5 rounded" />
                          <span className="capitalize">{role.name.replace(/_/g, ' ')}</span>
                        </label>
                      );
                    })}
                  </div>
                  {(userForm.role_ids || []).length === 0 && (
                    <p className="text-xs text-red-500 mt-1">Select at least one role</p>
                  )}
                </div>

                {/* Nurse-only inpatient/visit fee (doctor section already includes this field) */}
                {isNurseRole() && !isDoctorRole() && (
                  <div className="space-y-3 border-t pt-3">
                    <p className="text-sm font-semibold text-gray-700">Visit Fee</p>
                    <div>
                      <Label>Inpatient / Visit Fee (INR) <span className="text-red-500">*</span></Label>
                      <Input
                        required
                        value={userForm.inpatient_fee_inr}
                        onChange={(e) => setUserForm({ ...userForm, inpatient_fee_inr: e.target.value })}
                        placeholder="₹500"
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        Nursing charges on admissions bill once per day (not per visit). Room / room-type nursing rates are the primary source.
                      </p>
                    </div>
                  </div>
                )}

                {/* Doctor-specific fields */}
                {isDoctorRole() && (
                  <div className="space-y-3 border-t pt-3">
                    <p className="text-sm font-semibold text-gray-700">Doctor Profile</p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label>License Number</Label>
                        <Input value={userForm.license_number} onChange={(e) => setUserForm({ ...userForm, license_number: e.target.value })} placeholder="MH/MED/2020/12345" />
                      </div>
                      <div>
                        <Label>Specialization</Label>
                        <Input value={userForm.specialization} onChange={(e) => setUserForm({ ...userForm, specialization: e.target.value })} placeholder="Cardiology" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label>Qualifications</Label>
                        <Input value={userForm.qualification} onChange={(e) => setUserForm({ ...userForm, qualification: e.target.value })} placeholder="MD, FACC" />
                      </div>
                      <div>
                        <Label>Years of Experience</Label>
                        <Input type="number" value={userForm.experience_years} onChange={(e) => setUserForm({ ...userForm, experience_years: e.target.value })} placeholder="15" min="0" />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <Label>Consultation Fee</Label>
                        <Input value={userForm.consultation_fee_inr} onChange={(e) => setUserForm({ ...userForm, consultation_fee_inr: e.target.value })} placeholder="₹1500" />
                      </div>
                      <div>
                        <Label>Inpatient Fee <span className="text-red-500">*</span></Label>
                        <Input
                          required
                          value={userForm.inpatient_fee_inr}
                          onChange={(e) => setUserForm({ ...userForm, inpatient_fee_inr: e.target.value })}
                          placeholder="₹3000"
                        />
                      </div>
                      <div>
                        <Label>Emergency Fee</Label>
                        <Input value={userForm.emergency_fee_inr} onChange={(e) => setUserForm({ ...userForm, emergency_fee_inr: e.target.value })} placeholder="₹5000" />
                      </div>
                    </div>
                    <div>
                      <Label>Inpatient Fee Charge Mode</Label>
                      <select
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={userForm.inpatient_fee_charge_mode || 'per_day'}
                        onChange={(e) => setUserForm({ ...userForm, inpatient_fee_charge_mode: e.target.value })}
                      >
                        <option value="per_day">Per day — one charge per calendar day</option>
                        <option value="per_visit">Per visit — charge every recorded visit</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1">
                        {userForm.inpatient_fee_charge_mode === 'per_visit'
                          ? 'Every doctor visit during an admission is billed separately. Daily auto-post is off for this doctor.'
                          : 'At most one inpatient fee per day. Extra visits the same day are recorded but not charged again.'}
                      </p>
                    </div>
                  </div>
                )}

                {/* Doctor room-type visit rate overrides — shown once a doctor user exists (edit or post-create) */}
                {isDoctorRole() && editingUser && (
                  <div className="space-y-3 border-t pt-3">
                    <div>
                      <p className="text-sm font-semibold text-gray-700">Room-Type Visit Rates</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Override the base inpatient fee per room type. Leave blank to use the base fee (₹{userForm.inpatient_fee_inr || '—'}).
                        Rates follow the doctor&apos;s charge mode (per day or per visit).
                      </p>
                    </div>
                    <div className="border rounded overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-1.5 text-left font-medium">Room Type</th>
                            <th className="px-3 py-1.5 text-left font-medium">Visit Rate (₹)</th>
                            <th className="px-3 py-1.5"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {ROOM_TYPES.map(rt => {
                            const existing = doctorRoomRates.find(r => r.room_type === rt.value);
                            const editVal = doctorRoomRatesEdits[rt.value] ?? '';
                            return (
                              <tr key={rt.value} className="border-t">
                                <td className="px-3 py-1.5">{rt.label}</td>
                                <td className="px-3 py-1.5">
                                  <Input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    className="h-7 w-28 text-xs"
                                    placeholder={`${userForm.inpatient_fee_inr || '—'}`}
                                    value={editVal}
                                    onChange={e => setDoctorRoomRatesEdits(prev => ({ ...prev, [rt.value]: e.target.value }))}
                                  />
                                </td>
                                <td className="px-3 py-1.5 flex gap-1">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    className="h-6 text-xs px-2"
                                    disabled={!!doctorRoomRatesSaving[rt.value]}
                                    onClick={async () => {
                                      const val = doctorRoomRatesEdits[rt.value];
                                      if (!val || val === '') {
                                        // Delete override if exists
                                        if (existing) {
                                          setDoctorRoomRatesSaving(prev => ({ ...prev, [rt.value]: true }));
                                          try {
                                            await axios.delete(`/api/inpatient/doctor-room-rates/${existing.id}`);
                                            setDoctorRoomRates(prev => prev.filter(r => r.room_type !== rt.value));
                                            toast({ title: 'Cleared', description: `${rt.label} override removed.` });
                                          } catch (err) {
                                            toast({ title: 'Error', description: err.response?.data?.detail || 'Failed', variant: 'destructive' });
                                          } finally {
                                            setDoctorRoomRatesSaving(prev => ({ ...prev, [rt.value]: false }));
                                          }
                                        }
                                        return;
                                      }
                                      setDoctorRoomRatesSaving(prev => ({ ...prev, [rt.value]: true }));
                                      try {
                                        const res = await axios.post('/api/inpatient/doctor-room-rates', {
                                          doctor_id: editingUser.id,
                                          room_type: rt.value,
                                          visit_rate: parseFloat(val),
                                        });
                                        setDoctorRoomRates(prev => {
                                          const filtered = prev.filter(r => r.room_type !== rt.value);
                                          return [...filtered, res.data];
                                        });
                                        toast({ title: 'Saved', description: `${rt.label} rate set to ₹${val}.` });
                                      } catch (err) {
                                        toast({ title: 'Error', description: err.response?.data?.detail || 'Failed', variant: 'destructive' });
                                      } finally {
                                        setDoctorRoomRatesSaving(prev => ({ ...prev, [rt.value]: false }));
                                      }
                                    }}
                                  >
                                    {doctorRoomRatesSaving[rt.value] ? '...' : existing ? 'Update' : 'Set'}
                                  </Button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <input type="checkbox" id="is_active" checked={userForm.is_active}
                    onChange={(e) => setUserForm({ ...userForm, is_active: e.target.checked })} className="rounded" />
                  <Label htmlFor="is_active">Active User</Label>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t">
                  <Button type="button" variant="outline" onClick={() => { setShowUserForm(false); setEditingUser(null); }}>
                    {editingUser ? 'Done' : 'Cancel'}
                  </Button>
                  <Button type="submit" disabled={loading}>
                    {loading ? 'Saving...' : editingUser ? 'Update User' : 'Create User'}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>

          <Card>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="min-w-full table-auto">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2">User</th>
                      <th className="text-left py-2">Email</th>
                      <th className="text-left py-2">Role</th>
                      <th className="text-left py-2">Status</th>
                      <th className="text-left py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => {
                      const isSuperAdminRow = (user.user_roles || [user.user_role]).some(r => r.name === 'super_admin');
                      // Vendor super admin account: read-only for hospital admins
                      const canManageRow = !isSuperAdminRow || hasRole('super_admin');
                      return (
                      <tr key={user.id} className="border-b">
                        <td className="py-2">
                          <div>
                            <div className="font-medium">{user.first_name} {user.last_name}</div>
                            <div className="text-sm text-gray-600">@{user.username}</div>
                            {(user.user_roles || [user.user_role]).some(r => r.name === 'doctor') && user.specialization && (
                              <div className="text-xs text-blue-600">{user.specialization}</div>
                            )}
                          </div>
                        </td>
                        <td className="py-2">{user.email}</td>
                        <td className="py-2">
                          <div className="flex flex-wrap gap-1">
                            {(user.user_roles && user.user_roles.length > 0 ? user.user_roles : [user.user_role]).map((r, i) => (
                              <span key={i} className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs capitalize">
                                {r.name.replace(/_/g, ' ')}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-2">
                          <span className={`px-2 py-1 rounded-full text-xs ${
                            user.is_active 
                              ? 'bg-green-100 text-green-800' 
                              : 'bg-red-100 text-red-800'
                          }`}>
                            {user.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="py-2">
                          <div className="flex space-x-2">
                            {canManageRow && (
                              <>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => editUser(user)}
                                >
                                  <Edit className="h-4 w-4" />
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => { setPasswordResetUser(user); setNewPassword(''); }}
                                  title="Reset Password"
                                >
                                  <KeyRound className="h-4 w-4" />
                                </Button>
                              </>
                            )}
                            {!isSuperAdminRow && (
                              user.is_active ? (
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() => archiveUser(user.id, `${user.first_name} ${user.last_name}`)}
                                  title="Archive user"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-green-600 border-green-300 hover:bg-green-50"
                                  onClick={() => restoreUser(user.id)}
                                  title="Restore user"
                                >
                                  <RefreshCw className="h-4 w-4" />
                                </Button>
                              )
                            )}
                          </div>
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Roles & Permissions Tab — role CRUD (super_admin) + per-role feature grants (all admins) */}
      {activeTab === 'roles' && (
        <div className="space-y-6">
          {hasRole('super_admin') && (
          <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">Role Management</h2>
            <Button
              onClick={() => {
                setShowRoleForm(true);
                setEditingRole(null);
                setRoleForm({ name: '', description: '' });
              }}
              className="flex items-center"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Role
            </Button>
          </div>

          {showRoleForm && (
            <Card>
              <CardHeader>
                <CardTitle>{editingRole ? 'Edit Role' : 'Add New Role'}</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleRoleSubmit} className="space-y-4">
                  <div>
                    <Label htmlFor="role_name">Role Name</Label>
                    <Input
                      id="role_name"
                      value={roleForm.name}
                      onChange={(e) => setRoleForm({ ...roleForm, name: e.target.value })}
                      required
                    />
                  </div>

                  <div>
                    <Label htmlFor="role_description">Description</Label>
                    <Input
                      id="role_description"
                      value={roleForm.description}
                      onChange={(e) => setRoleForm({ ...roleForm, description: e.target.value })}
                    />
                  </div>

                  <div className="flex space-x-2">
                    <Button type="submit" disabled={loading}>
                      <Save className="h-4 w-4 mr-2" />
                      {loading ? 'Saving...' : 'Save Role'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setShowRoleForm(false);
                        setEditingRole(null);
                      }}
                    >
                      <X className="h-4 w-4 mr-2" />
                      Cancel
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent>
              <div className="space-y-4">
                {roles.map((role) => (
                  <div
                    key={role.id}
                    className="flex items-center justify-between p-4 border rounded-lg"
                  >
                    <div>
                      <h3 className="font-medium">{role.name}</h3>
                      <p className="text-sm text-gray-600">{role.description}</p>
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => editRole(role)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      {role.name !== 'super_admin' && (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => deleteRole(role.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          </div>
          )}

          <RolePermissionsEditor />
        </div>
      )}

      <ConfirmDialog
        open={confirmState.open}
        message={confirmState.message}
        onConfirm={() => { confirmState.onConfirm?.(); }}
        onCancel={() => setConfirmState({ open: false })}
      />

      {/* Reset Password Dialog */}
      <Dialog open={!!passwordResetUser} onOpenChange={(open) => { if (!open) { setPasswordResetUser(null); setNewPassword(''); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5" /> Reset Password
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-sm font-semibold">{passwordResetUser?.first_name} {passwordResetUser?.last_name}</p>
              <p className="text-xs text-gray-500">@{passwordResetUser?.username}</p>
            </div>
            <div>
              <Label>New Password *</Label>
              <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password" autoFocus />
              {newPassword && newPassword.length < 4 && (
                <p className="text-xs text-red-500 mt-1">Minimum 4 characters</p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setPasswordResetUser(null); setNewPassword(''); }}>Cancel</Button>
              <Button onClick={handleResetPassword} disabled={!newPassword || newPassword.length < 4}>
                Reset Password
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminModule;