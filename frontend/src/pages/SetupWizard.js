import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import {
  Building2, Database, UserCog, Shield, FolderSync,
  ChevronRight, ChevronLeft, Check, Plus, X, Eye, EyeOff,
  AlertCircle, CheckCircle2, FolderOpen, Upload, Cpu
} from 'lucide-react';

const STEPS = [
  { id: 'welcome',  title: 'Welcome',          icon: Building2 },
  { id: 'hospital', title: 'Hospital Info',     icon: Building2 },
  { id: 'database', title: 'Database Location', icon: Database },
  { id: 'admin',    title: 'Admin Account',     icon: UserCog },
  { id: 'license',  title: 'License',           icon: Shield },
  { id: 'backup',   title: 'Backup Locations',  icon: FolderSync },
  { id: 'review',   title: 'Review & Install',  icon: Check },
];

const SetupWizard = ({ onComplete }) => {
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [pathValidation, setPathValidation] = useState({});

  const [formData, setFormData] = useState({
    hospital_name: '',
    hospital_address1: '',
    hospital_address2: '',
    hospital_phone: '',
    hospital_email: '',
    db_location: '',
    admin_username: '',
    admin_email: '',
    admin_password: '',
    admin_confirm_password: '',
    admin_first_name: '',
    admin_last_name: '',
    backup_locations: [],
    license_file_content: '',
    license_filename: '',
  });

  const [newBackupPath, setNewBackupPath] = useState('');
  const [machineInfo, setMachineInfo] = useState(null);
  const [licenseInspect, setLicenseInspect] = useState(null);
  const [licenseChecking, setLicenseChecking] = useState(false);

  React.useEffect(() => {
    fetch('/api/license/machine-id')
      .then((r) => r.json())
      .then(setMachineInfo)
      .catch(() => setMachineInfo(null));
  }, []);

  const handleLicenseFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.lic')) {
      setLicenseInspect({ valid_signature: false, error: 'File must be a .lic license file' });
      return;
    }
    setLicenseChecking(true);
    setLicenseInspect(null);
    try {
      // Dry-run inspect (no DB write)
      const fd = new FormData();
      fd.append('file', file);
      const inspectRes = await fetch('/api/license/validate', { method: 'POST', body: fd });
      const inspectData = await inspectRes.json();
      setLicenseInspect(inspectData);
      // Stash the raw text so we can ship it to /api/setup/complete
      const text = await file.text();
      updateField('license_file_content', text);
      updateField('license_filename', file.name);
    } catch (err) {
      setLicenseInspect({ valid_signature: false, error: 'Could not validate license file' });
    } finally {
      setLicenseChecking(false);
      e.target.value = '';
    }
  };

  const clearLicense = () => {
    updateField('license_file_content', '');
    updateField('license_filename', '');
    setLicenseInspect(null);
  };

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setError('');
  };

  const validatePath = async (path, key) => {
    if (!path.trim()) {
      setPathValidation(prev => ({ ...prev, [key]: null }));
      return;
    }
    try {
      const res = await fetch('/api/setup/validate-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      setPathValidation(prev => ({ ...prev, [key]: data }));
    } catch {
      setPathValidation(prev => ({ ...prev, [key]: { valid: false, message: 'Could not validate path' } }));
    }
  };

  const [browsing, setBrowsing] = useState(false);

  const browseFolder = async (onSelect) => {
    setBrowsing(true);
    try {
      const res = await fetch('/api/setup/browse-folder');
      const data = await res.json();
      if (data.path) {
        onSelect(data.path);
      }
    } catch {
      // Folder picker not available (e.g. dev mode without tkinter)
    } finally {
      setBrowsing(false);
    }
  };

  const addBackupLocation = () => {
    const path = newBackupPath.trim();
    if (path && !formData.backup_locations.includes(path)) {
      updateField('backup_locations', [...formData.backup_locations, path]);
      setNewBackupPath('');
    }
  };

  const removeBackupLocation = (index) => {
    updateField('backup_locations', formData.backup_locations.filter((_, i) => i !== index));
  };

  const canProceed = () => {
    switch (STEPS[step].id) {
      case 'hospital':
        return formData.hospital_name.trim().length > 0;
      case 'admin':
        return (
          formData.admin_username.trim().length >= 3 &&
          formData.admin_email.trim().includes('@') &&
          formData.admin_password.length >= 6 &&
          formData.admin_password === formData.admin_confirm_password
        );
      case 'license':
        // Step is optional, but if a file IS chosen it must be valid for this machine
        if (!formData.license_file_content) return true;
        return !!(licenseInspect && licenseInspect.valid_signature && licenseInspect.machine_match);
      default:
        return true;
    }
  };

  const handleComplete = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/setup/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hospital_name: formData.hospital_name,
          hospital_address: [formData.hospital_address1, formData.hospital_address2].filter(Boolean).join(', '),
          hospital_phone: formData.hospital_phone,
          hospital_email: formData.hospital_email,
          db_location: formData.db_location,
          admin_username: formData.admin_username,
          admin_email: formData.admin_email,
          admin_password: formData.admin_password,
          admin_first_name: formData.admin_first_name || 'System',
          admin_last_name: formData.admin_last_name || 'Administrator',
          backup_locations: formData.backup_locations,
          license_file_content: formData.license_file_content || '',
        }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        onComplete();
      } else {
        setError(data.detail || 'Setup failed. Please try again.');
      }
    } catch (err) {
      setError('Connection error. Is the server running?');
    } finally {
      setLoading(false);
    }
  };

  const renderStepContent = () => {
    switch (STEPS[step].id) {
      case 'welcome':
        return (
          <div className="text-center space-y-6 py-8">
            <div className="mx-auto w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center">
              <Building2 className="w-10 h-10 text-primary" />
            </div>
            <div>
              <h2 className="text-2xl font-bold">Welcome to KT HEALTH ERP</h2>
              <p className="text-muted-foreground mt-2 max-w-md mx-auto">
                Let's set up your system. This wizard will configure your database,
                create an admin account, and set up backup locations.
              </p>
            </div>
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800 max-w-md mx-auto">
              This setup runs only once. All settings can be updated later from the admin panel.
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 max-w-md mx-auto">
              You're seeing this wizard because the Windows installer's setup pages were
              skipped (typical for source installs and recovery). On a normal installer-based
              install, the same questions are asked during installation and the app boots
              straight into login.
            </div>
          </div>
        );

      case 'hospital':
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="hospital_name">Hospital Name *</Label>
              <Input
                id="hospital_name"
                value={formData.hospital_name}
                onChange={(e) => updateField('hospital_name', e.target.value)}
                placeholder="City General Hospital"
                autoFocus
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="hospital_address1">Address Line 1</Label>
                <Input
                  id="hospital_address1"
                  value={formData.hospital_address1}
                  onChange={(e) => updateField('hospital_address1', e.target.value)}
                  placeholder="Building / Street"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="hospital_address2">Address Line 2</Label>
                <Input
                  id="hospital_address2"
                  value={formData.hospital_address2}
                  onChange={(e) => updateField('hospital_address2', e.target.value)}
                  placeholder="City, State, PIN"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="hospital_phone">Phone</Label>
                <Input
                  id="hospital_phone"
                  value={formData.hospital_phone}
                  onChange={(e) => updateField('hospital_phone', e.target.value)}
                  placeholder="+91-9876543210"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="hospital_email">Email</Label>
                <Input
                  id="hospital_email"
                  value={formData.hospital_email}
                  onChange={(e) => updateField('hospital_email', e.target.value)}
                  placeholder="info@hospital.com"
                />
              </div>
            </div>
          </div>
        );

      case 'database':
        return (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
              Choose where to store your database. Leave empty to use the default location
              (a <code className="bg-amber-100 px-1 rounded">data</code> folder next to the application).
            </div>
            <div className="space-y-2">
              <Label htmlFor="db_location">Database Folder Path</Label>
              <div className="flex gap-2">
                <Input
                  id="db_location"
                  value={formData.db_location}
                  onChange={(e) => updateField('db_location', e.target.value)}
                  onBlur={(e) => validatePath(e.target.value, 'db')}
                  placeholder="Leave empty for default location"
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => browseFolder((path) => {
                    updateField('db_location', path);
                    validatePath(path, 'db');
                  })}
                  disabled={browsing}
                >
                  <FolderOpen className="w-4 h-4 mr-1" />
                  {browsing ? 'Opening...' : 'Browse'}
                </Button>
              </div>
              {pathValidation.db && (
                <div className={`flex items-center gap-2 text-sm ${pathValidation.db.valid ? 'text-green-600' : 'text-red-600'}`}>
                  {pathValidation.db.valid ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                  {pathValidation.db.message}
                </div>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              <p>The database file <code className="bg-gray-100 px-1 rounded">kthealth_erp.db</code> will be created in this folder.</p>
              <p className="mt-1">Examples: <code className="bg-gray-100 px-1 rounded">D:\KTHealthData</code> or <code className="bg-gray-100 px-1 rounded">C:\Users\Admin\Documents\KTHEALTHERP</code></p>
            </div>
          </div>
        );

      case 'admin':
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="admin_first_name">First Name</Label>
                <Input
                  id="admin_first_name"
                  value={formData.admin_first_name}
                  onChange={(e) => updateField('admin_first_name', e.target.value)}
                  placeholder="System"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin_last_name">Last Name</Label>
                <Input
                  id="admin_last_name"
                  value={formData.admin_last_name}
                  onChange={(e) => updateField('admin_last_name', e.target.value)}
                  placeholder="Administrator"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin_username">Username *</Label>
              <Input
                id="admin_username"
                value={formData.admin_username}
                onChange={(e) => updateField('admin_username', e.target.value)}
                placeholder="admin"
                autoComplete="off"
              />
              {formData.admin_username && formData.admin_username.length < 3 && (
                <p className="text-sm text-red-500">Username must be at least 3 characters</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin_email">Email *</Label>
              <Input
                id="admin_email"
                type="email"
                value={formData.admin_email}
                onChange={(e) => updateField('admin_email', e.target.value)}
                placeholder="admin@hospital.com"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin_password">Password *</Label>
              <div className="relative">
                <Input
                  id="admin_password"
                  type={showPassword ? 'text' : 'password'}
                  value={formData.admin_password}
                  onChange={(e) => updateField('admin_password', e.target.value)}
                  placeholder="Minimum 6 characters"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {formData.admin_password && formData.admin_password.length < 6 && (
                <p className="text-sm text-red-500">Password must be at least 6 characters</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin_confirm_password">Confirm Password *</Label>
              <Input
                id="admin_confirm_password"
                type={showPassword ? 'text' : 'password'}
                value={formData.admin_confirm_password}
                onChange={(e) => updateField('admin_confirm_password', e.target.value)}
                placeholder="Re-enter password"
                autoComplete="new-password"
              />
              {formData.admin_confirm_password && formData.admin_password !== formData.admin_confirm_password && (
                <p className="text-sm text-red-500">Passwords do not match</p>
              )}
            </div>
          </div>
        );

      case 'license':
        return (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
              Each license is bound to <strong>this specific machine</strong>.
              Send your machine ID to your vendor to receive a <code>.lic</code> file,
              then upload it here. This step is optional — you can upload the
              license later from <strong>Dashboard &gt; License</strong>.
            </div>

            {machineInfo && (
              <div className="space-y-2">
                <Label>This machine&apos;s ID</Label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-lg font-bold tracking-widest bg-gray-100 px-3 py-2 rounded select-all">
                    {machineInfo.machine_id}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      navigator.clipboard.writeText(machineInfo.machine_id);
                    }}
                  >
                    Copy
                  </Button>
                </div>
                <p className="text-xs text-gray-500 flex items-center gap-1">
                  <Cpu className="w-3 h-3" />
                  {machineInfo.hostname} · {machineInfo.os}
                </p>
              </div>
            )}

            <div className="space-y-2">
              <Label>License file (.lic)</Label>
              <div className="flex items-center gap-2">
                <input
                  type="file"
                  accept=".lic"
                  onChange={handleLicenseFile}
                  className="hidden"
                  id="wizard-license-upload"
                />
                <label htmlFor="wizard-license-upload" className="flex-1">
                  <Button asChild variant="outline" className="w-full">
                    <span>
                      <Upload className="w-4 h-4 mr-2" />
                      {formData.license_filename || 'Choose .lic file'}
                    </span>
                  </Button>
                </label>
                {formData.license_filename && (
                  <Button type="button" variant="outline" onClick={clearLicense}>
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
              {licenseChecking && (
                <p className="text-sm text-muted-foreground">Verifying license…</p>
              )}
            </div>

            {licenseInspect && !licenseChecking && (
              <div className={`rounded-lg p-4 text-sm border ${
                licenseInspect.valid_signature && licenseInspect.machine_match
                  ? 'bg-green-50 border-green-200 text-green-800'
                  : 'bg-red-50 border-red-200 text-red-800'
              }`}>
                {!licenseInspect.valid_signature ? (
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold">Invalid license</div>
                      <div>{licenseInspect.error || 'Signature verification failed.'}</div>
                    </div>
                  </div>
                ) : !licenseInspect.machine_match ? (
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold">Wrong machine</div>
                      <div>
                        License is bound to{' '}
                        <code>{licenseInspect.license_machine_id}</code> but this
                        machine is <code>{licenseInspect.current_machine_id}</code>.
                      </div>
                      <div className="mt-1 text-xs">
                        Ask your vendor to re-issue the license for this machine
                        (or use the rebind flow on the License page after setup).
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <div className="font-semibold">License is valid for this machine</div>
                      <div>{licenseInspect.hospital_name} · {licenseInspect.plan} plan</div>
                      <div>
                        Expires {licenseInspect.expires_at
                          ? new Date(licenseInspect.expires_at).toLocaleDateString()
                          : 'unknown'}
                        {' '}({licenseInspect.days_remaining} days remaining)
                      </div>
                      {(licenseInspect.features || []).length > 0 && (
                        <div className="text-xs">
                          Modules: {licenseInspect.features.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );

      case 'backup':
        return (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
              Add folder paths where database backups will be saved.
              You can use network drives, USB drives, or any accessible folder.
              This step is optional and can be configured later.
            </div>
            <div className="flex gap-2">
              <Input
                value={newBackupPath}
                onChange={(e) => setNewBackupPath(e.target.value)}
                placeholder="E:\Backups\KTHEALTHERP"
                onKeyDown={(e) => e.key === 'Enter' && addBackupLocation()}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => browseFolder((path) => setNewBackupPath(path))}
                disabled={browsing}
              >
                <FolderOpen className="w-4 h-4 mr-1" />
                {browsing ? 'Opening...' : 'Browse'}
              </Button>
              <Button type="button" variant="outline" onClick={addBackupLocation} disabled={!newBackupPath.trim()}>
                <Plus className="w-4 h-4 mr-1" /> Add
              </Button>
            </div>
            {formData.backup_locations.length > 0 ? (
              <div className="space-y-2">
                {formData.backup_locations.map((loc, i) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 border">
                    <div className="flex items-center gap-2 text-sm">
                      <FolderSync className="w-4 h-4 text-muted-foreground" />
                      <code>{loc}</code>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeBackupLocation(i)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                No backup locations added. You can configure this later from the admin panel.
              </p>
            )}
          </div>
        );

      case 'review':
        return (
          <div className="space-y-4">
            <div className="divide-y rounded-lg border">
              <ReviewRow label="Hospital Name" value={formData.hospital_name} />
              <ReviewRow label="Address" value={[formData.hospital_address1, formData.hospital_address2].filter(Boolean).join(', ') || 'Not provided'} />
              <ReviewRow label="Phone" value={formData.hospital_phone || 'Not provided'} />
              <ReviewRow label="Database Location" value={formData.db_location || 'Default (data/ folder)'} />
              <ReviewRow label="Admin Username" value={formData.admin_username} />
              <ReviewRow label="Admin Email" value={formData.admin_email} />
              <ReviewRow
                label="License"
                value={formData.license_filename
                  ? `${formData.license_filename} (verified for this machine)`
                  : 'Will upload later'}
              />
              <ReviewRow
                label="Backup Locations"
                value={formData.backup_locations.length > 0
                  ? formData.backup_locations.join(', ')
                  : 'None configured'}
              />
            </div>
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-sm text-green-800">
              Click <strong>Complete Setup</strong> to initialize the system.
              The database will be created and your admin account will be ready to use.
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
              After setup, log in with your admin credentials and go to{' '}
              <strong>Dashboard &gt; License</strong> to upload your license file (.lic).
              Without a license, only admin users can log in.
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-2xl">
        {/* Step indicators */}
        <div className="flex items-center justify-center mb-8 gap-1">
          {STEPS.map((s, i) => (
            <React.Fragment key={s.id}>
              <div
                className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium transition-colors ${
                  i === step
                    ? 'bg-primary text-white'
                    : i < step
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-400'
                }`}
              >
                {i < step ? (
                  <Check className="w-3 h-3" />
                ) : (
                  <s.icon className="w-3 h-3" />
                )}
                <span className="hidden sm:inline">{s.title}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-6 h-0.5 ${i < step ? 'bg-green-300' : 'bg-gray-200'}`} />
              )}
            </React.Fragment>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {React.createElement(STEPS[step].icon, { className: 'w-5 h-5' })}
              {STEPS[step].title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {renderStepContent()}

            {error && (
              <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            <div className="flex justify-between mt-8">
              <Button
                variant="outline"
                onClick={() => setStep(step - 1)}
                disabled={step === 0}
              >
                <ChevronLeft className="w-4 h-4 mr-1" /> Back
              </Button>

              {step < STEPS.length - 1 ? (
                <Button
                  onClick={() => setStep(step + 1)}
                  disabled={!canProceed()}
                >
                  Next <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              ) : (
                <Button
                  onClick={handleComplete}
                  disabled={loading}
                  className="bg-green-600 hover:bg-green-700"
                >
                  {loading ? 'Setting up...' : 'Complete Setup'}
                  {!loading && <Check className="w-4 h-4 ml-1" />}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const ReviewRow = ({ label, value }) => (
  <div className="flex justify-between py-3 px-4">
    <span className="text-sm text-muted-foreground">{label}</span>
    <span className="text-sm font-medium text-right max-w-[60%] break-all">{value}</span>
  </div>
);

export default SetupWizard;
