import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../hooks/use-toast';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import {
  Settings,
  Users,
  Shield,
  ToggleLeft,
  Plus,
  Edit,
  Trash2,
  Save,
  X,
  RefreshCw
} from 'lucide-react';
import axios from 'axios';

const AdminModule = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [modules, setModules] = useState([]);
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [activeTab, setActiveTab] = useState(user?.role === 'super_admin' ? 'modules' : 'users');
  const [showUserForm, setShowUserForm] = useState(false);
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [editingRole, setEditingRole] = useState(null);
  const [loading, setLoading] = useState(false);
  const [confirmState, setConfirmState] = useState({ open: false });

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
    emergency_fee_inr: '',
    specialization: '',
    qualification: '',
    experience_years: ''
  });

  const [roleForm, setRoleForm] = useState({
    name: '',
    description: ''
  });

  useEffect(() => {
    if (user?.role === 'super_admin' || user?.role === 'hospital_admin') {
      if (user?.role === 'super_admin') {
        fetchModules();
      }
      fetchUsers();
      fetchRoles();
    }
  }, [user]);

  const fetchModules = async () => {
    try {
      const response = await axios.get('/api/admin/modules');
      setModules(response.data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to fetch modules"
      });
    }
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

  const toggleModule = async (moduleId, currentStatus) => {
    try {
      await axios.put(`/api/admin/modules/${moduleId}`, {
        is_enabled: !currentStatus
      });
      
      toast({
        title: "Success",
        description: "Module status updated successfully"
      });
      
      fetchModules();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to update module status"
      });
    }
  };

  const handleUserSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const roleIds = userForm.role_ids.length > 0 ? userForm.role_ids : [];
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
        emergency_fee_inr: '',
        specialization: '',
        qualification: '',
        experience_years: ''
      });
      fetchUsers();
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
          fetchUsers();
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
      fetchUsers();
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error",
        description: error.response?.data?.detail || "Failed to restore user"
      });
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

  const editUser = (user) => {
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
      emergency_fee_inr: user.emergency_fee_inr || '',
      specialization: user.specialization || '',
      qualification: user.qualification || '',
      experience_years: user.experience_years || ''
    });
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
    return (userForm.role_ids || []).some(rid => {
      const r = roles.find(role => role.id === rid);
      return r?.name === 'doctor';
    });
  };

  if (!(user?.roles || [user?.role]).includes('super_admin') && !(user?.roles || [user?.role]).includes('hospital_admin')) {
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">System Administration</h1>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {user?.role === 'super_admin' && (
            <button
              onClick={() => setActiveTab('modules')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'modules'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Settings className="inline h-4 w-4 mr-2" />
              Module Management
            </button>
          )}
          <button
            onClick={() => setActiveTab('users')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'users'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Users className="inline h-4 w-4 mr-2" />
            User Management
          </button>
          {user?.role === 'super_admin' && (
            <button
              onClick={() => setActiveTab('roles')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'roles'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Shield className="inline h-4 w-4 mr-2" />
              Role Management
            </button>
          )}
        </nav>
      </div>

      {/* Module Management Tab - Super Admin Only */}
      {activeTab === 'modules' && user?.role === 'super_admin' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Settings className="mr-2 h-5 w-5" />
              System Modules
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {modules.map((module) => (
                <div
                  key={module.id}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div>
                    <h3 className="font-medium">{module.display_name}</h3>
                    <p className="text-sm text-gray-600">{module.description}</p>
                    {module.is_always_enabled && (
                      <p className="text-xs text-blue-600 mt-1">Always enabled</p>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      variant={module.is_enabled ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleModule(module.id, module.is_enabled)}
                      disabled={module.is_always_enabled}
                      className="flex items-center"
                    >
                      <ToggleLeft className="h-4 w-4 mr-1" />
                      {module.is_enabled ? 'Enabled' : 'Disabled'}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* User Management Tab */}
      {activeTab === 'users' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">User Management</h2>
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
                  is_active: true,
                  consultation_fee: '',
                  specialization: '',
                  qualification: '',
                  experience_years: ''
                });
              }}
              className="flex items-center"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add User
            </Button>
          </div>

          {showUserForm && (
            <Card>
              <CardHeader>
                <CardTitle>{editingUser ? 'Edit User' : 'Add New User'}</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleUserSubmit} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="username">Username</Label>
                      <Input
                        id="username"
                        value={userForm.username}
                        onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        value={userForm.email}
                        onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                        required
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="first_name">First Name</Label>
                      <Input
                        id="first_name"
                        value={userForm.first_name}
                        onChange={(e) => setUserForm({ ...userForm, first_name: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="last_name">Last Name</Label>
                      <Input
                        id="last_name"
                        value={userForm.last_name}
                        onChange={(e) => setUserForm({ ...userForm, last_name: e.target.value })}
                        required
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="phone">Phone</Label>
                      <Input
                        id="phone"
                        value={userForm.phone}
                        onChange={(e) => setUserForm({ ...userForm, phone: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>Roles *</Label>
                      <div className="border border-gray-300 rounded-md p-2 mt-1 max-h-40 overflow-y-auto space-y-1">
                        {roles.map((role) => (
                          <label key={role.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-50 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={userForm.role_ids.includes(role.id)}
                              onChange={(e) => {
                                const ids = e.target.checked
                                  ? [...userForm.role_ids, role.id]
                                  : userForm.role_ids.filter(id => id !== role.id);
                                setUserForm({ ...userForm, role_ids: ids, role_id: ids[0] || '' });
                              }}
                              className="w-4 h-4 rounded border-gray-300"
                            />
                            <span className="text-sm capitalize">{role.name.replace(/_/g, ' ')}</span>
                          </label>
                        ))}
                      </div>
                      {userForm.role_ids.length === 0 && (
                        <p className="text-xs text-red-500 mt-1">Select at least one role</p>
                      )}
                    </div>
                  </div>

                  {!editingUser && (
                    <div>
                      <Label htmlFor="password">Password</Label>
                      <Input
                        id="password"
                        type="password"
                        value={userForm.password}
                        onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                        required={!editingUser}
                      />
                    </div>
                  )}

                  {/* Doctor-specific fields */}
                  {isDoctorRole() && (
                    <div className="space-y-4 border-t pt-4">
                      <h3 className="text-lg font-medium text-gray-900">Doctor Profile Information</h3>
                      
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="license_number">License Number</Label>
                          <Input
                            id="license_number"
                            value={userForm.license_number}
                            onChange={(e) => setUserForm({ ...userForm, license_number: e.target.value })}
                            placeholder="e.g., MH/MED/2020/12345"
                          />
                        </div>
                        <div>
                          <Label htmlFor="specialization">Specialization</Label>
                          <Input
                            id="specialization"
                            value={userForm.specialization}
                            onChange={(e) => setUserForm({ ...userForm, specialization: e.target.value })}
                            placeholder="e.g., Cardiology"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="qualification">Qualifications</Label>
                          <Input
                            id="qualification"
                            value={userForm.qualification}
                            onChange={(e) => setUserForm({ ...userForm, qualification: e.target.value })}
                            placeholder="e.g., MD, FACC"
                          />
                        </div>
                        <div>
                          <Label htmlFor="experience_years">Years of Experience</Label>
                          <Input
                            id="experience_years"
                            type="number"
                            value={userForm.experience_years}
                            onChange={(e) => setUserForm({ ...userForm, experience_years: e.target.value })}
                            placeholder="e.g., 15"
                            min="0"
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <h4 className="text-md font-medium text-gray-700">Fee Structure (INR)</h4>
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <Label htmlFor="consultation_fee_inr">Consultation Fee</Label>
                            <Input
                              id="consultation_fee_inr"
                              value={userForm.consultation_fee_inr}
                              onChange={(e) => setUserForm({ ...userForm, consultation_fee_inr: e.target.value })}
                              placeholder="e.g., ₹1500"
                            />
                          </div>
                          <div>
                            <Label htmlFor="inpatient_fee_inr">Inpatient Fee</Label>
                            <Input
                              id="inpatient_fee_inr"
                              value={userForm.inpatient_fee_inr}
                              onChange={(e) => setUserForm({ ...userForm, inpatient_fee_inr: e.target.value })}
                              placeholder="e.g., ₹3000"
                            />
                          </div>
                          <div>
                            <Label htmlFor="emergency_fee_inr">Emergency Fee</Label>
                            <Input
                              id="emergency_fee_inr"
                              value={userForm.emergency_fee_inr}
                              onChange={(e) => setUserForm({ ...userForm, emergency_fee_inr: e.target.value })}
                              placeholder="e.g., ₹5000"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="is_active"
                      checked={userForm.is_active}
                      onChange={(e) => setUserForm({ ...userForm, is_active: e.target.checked })}
                    />
                    <Label htmlFor="is_active">Active User</Label>
                  </div>

                  <div className="flex space-x-2">
                    <Button type="submit" disabled={loading}>
                      <Save className="h-4 w-4 mr-2" />
                      {loading ? 'Saving...' : 'Save User'}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setShowUserForm(false);
                        setEditingUser(null);
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
                    {users.map((user) => (
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
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => editUser(user)}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            {!(user.user_roles || [user.user_role]).some(r => r.name === 'super_admin') && (
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
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Role Management Tab - Super Admin Only */}
      {activeTab === 'roles' && user?.role === 'super_admin' && (
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

      <ConfirmDialog
        open={confirmState.open}
        message={confirmState.message}
        onConfirm={() => { confirmState.onConfirm?.(); }}
        onCancel={() => setConfirmState({ open: false })}
      />
    </div>
  );
};

export default AdminModule;