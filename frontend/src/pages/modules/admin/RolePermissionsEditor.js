import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { useToast } from '../../../hooks/use-toast';
import axios from 'axios';
import { ShieldCheck, Save, Loader2 } from 'lucide-react';

/**
 * Self-contained editor for feature-level, per-role permission grants.
 * Loads roles + the module-permission catalog on mount, then lets an admin
 * toggle granular permissions for the selected role/module.
 */
const RolePermissionsEditor = () => {
  const { toast } = useToast();
  const [rolesList, setRolesList] = useState([]);
  const [selectedRoleId, setSelectedRoleId] = useState(null);
  const [modulePermissionsCatalog, setModulePermissionsCatalog] = useState([]);
  const [selectedPermModule, setSelectedPermModule] = useState('inpatient');
  const [roleGrants, setRoleGrants] = useState({});
  const [permDirty, setPermDirty] = useState(false);
  const [permSaving, setPermSaving] = useState(false);

  useEffect(() => {
    fetchRolesList();
    fetchModulePermissionsCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedRoleId) fetchRoleGrants(selectedRoleId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRoleId]);

  const fetchRolesList = async () => {
    try {
      const res = await axios.get('/api/admin/roles');
      const roles = (res.data || []).filter(r => !['super_admin', 'hospital_admin'].includes(r.name));
      setRolesList(roles);
      if (!selectedRoleId && roles.length > 0) {
        setSelectedRoleId(roles[0].id);
      }
    } catch { /* silent */ }
  };

  const fetchModulePermissionsCatalog = async () => {
    try {
      const res = await axios.get('/api/admin/module-permissions');
      setModulePermissionsCatalog(res.data || []);
    } catch { /* silent */ }
  };

  const fetchRoleGrants = async (roleId) => {
    if (!roleId) return;
    try {
      const res = await axios.get(`/api/admin/roles/${roleId}/permissions`);
      const byModule = {};
      (res.data.grants || []).forEach(g => { byModule[g.module_name] = g.permissions || []; });
      setRoleGrants(byModule);
      setPermDirty(false);
    } catch {
      setRoleGrants({});
    }
  };

  const togglePermission = (perm) => {
    setRoleGrants(prev => {
      const current = prev[selectedPermModule] || [];
      const next = current.includes(perm) ? current.filter(p => p !== perm) : [...current, perm];
      return { ...prev, [selectedPermModule]: next };
    });
    setPermDirty(true);
  };

  const handleSaveRolePermissions = async () => {
    setPermSaving(true);
    try {
      await axios.put(`/api/admin/roles/${selectedRoleId}/permissions`, {
        module_name: selectedPermModule,
        permissions: roleGrants[selectedPermModule] || [],
      });
      toast({ title: 'Permissions saved', description: `Updated for module: ${selectedPermModule}` });
      setPermDirty(false);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to save';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setPermSaving(false); }
  };

  const modulesInCatalog = Array.from(new Set(modulePermissionsCatalog.map(p => p.module_name))).sort();
  const currentModulePerms = modulePermissionsCatalog.filter(p => p.module_name === selectedPermModule);
  const byCategory = currentModulePerms.reduce((acc, p) => {
    const cat = p.category || 'user';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(p);
    return acc;
  }, {});
  const granted = new Set(roleGrants[selectedPermModule] || []);
  const allForModule = currentModulePerms.map(p => p.permission_name);
  const allGranted = allForModule.length > 0 && allForModule.every(p => granted.has(p));
  const noneGranted = allForModule.every(p => !granted.has(p));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <ShieldCheck className="h-5 w-5 mr-2" />
          Role Permissions
        </CardTitle>
        <p className="text-sm text-gray-500 mt-1">
          Grant or revoke feature-level permissions per role. Super Admin and Hospital Admin bypass all permission checks and are not listed.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Role selector */}
        <div className="flex flex-wrap gap-2">
          {rolesList.length === 0 ? (
            <p className="text-sm text-gray-500">Loading roles…</p>
          ) : (
            rolesList.map(r => (
              <Button
                key={r.id}
                size="sm"
                variant={selectedRoleId === r.id ? 'default' : 'outline'}
                onClick={() => {
                  if (permDirty && !window.confirm('Discard unsaved permission changes?')) return;
                  setSelectedRoleId(r.id);
                }}
              >
                {r.name.replace(/_/g, ' ')}
              </Button>
            ))
          )}
        </div>

        {/* Module tabs */}
        {modulesInCatalog.length > 0 && (
          <div className="flex gap-1 border-b">
            {modulesInCatalog.map(m => (
              <button
                key={m}
                type="button"
                className={`px-3 py-1.5 text-sm ${
                  selectedPermModule === m
                    ? 'border-b-2 border-blue-600 font-semibold text-blue-700'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => {
                  if (permDirty && !window.confirm('Discard unsaved permission changes?')) return;
                  setSelectedPermModule(m);
                }}
              >
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        )}

        {/* Permission grid */}
        {!selectedRoleId ? (
          <p className="text-sm text-gray-500 text-center py-6">Select a role to edit its permissions.</p>
        ) : currentModulePerms.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-6">No permissions defined for module "{selectedPermModule}".</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div className="text-xs text-gray-500">
                {granted.size} / {allForModule.length} granted
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={allGranted}
                  onClick={() => {
                    setRoleGrants(prev => ({ ...prev, [selectedPermModule]: allForModule }));
                    setPermDirty(true);
                  }}
                >
                  Select All
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={noneGranted}
                  onClick={() => {
                    setRoleGrants(prev => ({ ...prev, [selectedPermModule]: [] }));
                    setPermDirty(true);
                  }}
                >
                  Clear All
                </Button>
              </div>
            </div>

            {/* Categorised list */}
            {Object.entries(byCategory).sort().map(([cat, perms]) => (
              <div key={cat} className="border rounded-lg p-3">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 capitalize">{cat}</h4>
                <div className="grid md:grid-cols-2 gap-2">
                  {perms.map(p => (
                    <label key={p.id} className="flex items-start gap-2 p-2 rounded hover:bg-gray-50 cursor-pointer">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={granted.has(p.permission_name)}
                        onChange={() => togglePermission(p.permission_name)}
                      />
                      <div className="flex-1 text-sm">
                        <div className="font-medium font-mono text-xs">{p.permission_name}</div>
                        {p.permission_description && (
                          <div className="text-xs text-gray-500">{p.permission_description}</div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            ))}

            {/* Save bar */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              {permDirty && <span className="text-xs text-orange-600">Unsaved changes</span>}
              <Button
                variant="outline"
                onClick={() => fetchRoleGrants(selectedRoleId)}
                disabled={!permDirty || permSaving}
              >
                Discard
              </Button>
              <Button
                onClick={handleSaveRolePermissions}
                disabled={!permDirty || permSaving}
              >
                {permSaving ? (
                  <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Saving…</>
                ) : (
                  <><Save className="h-4 w-4 mr-1" /> Save Permissions</>
                )}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default RolePermissionsEditor;
