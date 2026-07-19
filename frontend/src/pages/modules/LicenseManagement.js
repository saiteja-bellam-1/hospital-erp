import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Upload, Shield, CheckCircle, AlertTriangle, XCircle, Clock, Cpu, Send, Download } from 'lucide-react';
import axios from 'axios';

const LicenseManagement = () => {
  const [license, setLicense] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [machineInfo, setMachineInfo] = useState(null);
  const [pending, setPending] = useState(null); // { file, inspect, checking }
  const [rebinding, setRebinding] = useState(false);

  const fetchLicenseStatus = async () => {
    try {
      const response = await axios.get('/api/license/status');
      setLicense(response.data);
    } catch (error) {
      console.error('Failed to fetch license status:', error);
      setLicense({ status: 'no_license', message: 'Unable to fetch license status' });
    } finally {
      setLoading(false);
    }
  };

  const fetchMachineId = async () => {
    try {
      const res = await axios.get('/api/license/machine-id');
      setMachineInfo(res.data);
    } catch {}
  };

  useEffect(() => {
    fetchLicenseStatus();
    fetchMachineId();
  }, []);

  const handleFilePicked = async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (!file.name.endsWith('.lic')) {
      setMessage({ type: 'error', text: 'Please choose a valid .lic license file' });
      return;
    }
    setMessage(null);
    setPending({ file, checking: true, inspect: null });
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await axios.post('/api/license/validate', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPending({ file, checking: false, inspect: res.data });
    } catch (err) {
      setPending({
        file,
        checking: false,
        inspect: {
          valid_signature: false,
          error: err.response?.data?.detail || 'Could not validate license',
        },
      });
    }
  };

  const applyPending = async () => {
    if (!pending?.file) return;
    setUploading(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append('file', pending.file);
      const response = await axios.post('/api/license/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMessage({ type: 'success', text: response.data.message });
      setLicense(response.data.license);
      setPending(null);
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Failed to upload license file',
      });
    } finally {
      setUploading(false);
    }
  };

  const downloadRebindRequest = async () => {
    setRebinding(true);
    setMessage(null);
    try {
      const res = await axios.get('/api/license/rebind-request', { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/json' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^";]+)"?/);
      const fname = m ? m[1] : 'kthealth_rebind.rebind.json';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage({
        type: 'success',
        text: 'Rebind request downloaded. Send this file to your vendor — they will return a fresh .lic bound to this machine.',
      });
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Could not generate rebind request',
      });
    } finally {
      setRebinding(false);
    }
  };

  const getStatusBadge = (status) => {
    const configs = {
      active: { variant: 'default', className: 'bg-green-100 text-green-800', icon: <CheckCircle className="h-3 w-3" />, label: 'Active' },
      expiring_soon: { variant: 'default', className: 'bg-yellow-100 text-yellow-800', icon: <AlertTriangle className="h-3 w-3" />, label: 'Expiring Soon' },
      grace_period: { variant: 'default', className: 'bg-red-100 text-red-800', icon: <Clock className="h-3 w-3" />, label: 'Grace Period' },
      expired: { variant: 'destructive', className: '', icon: <XCircle className="h-3 w-3" />, label: 'Expired' },
      machine_mismatch: { variant: 'destructive', className: '', icon: <Cpu className="h-3 w-3" />, label: 'Machine Mismatch' },
      no_license: { variant: 'secondary', className: '', icon: <Shield className="h-3 w-3" />, label: 'No License' },
    };
    const config = configs[status] || configs.no_license;
    return (
      <Badge variant={config.variant} className={`${config.className} flex items-center gap-1`}>
        {config.icon} {config.label}
      </Badge>
    );
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading license information...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">License Management</h1>
        {getStatusBadge(license?.status)}
      </div>

      {message && (
        <div className={`p-4 rounded-lg ${message.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {message.text}
        </div>
      )}

      {/* Machine ID Card */}
      {machineInfo && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Machine ID</CardTitle>
            <CardDescription>Share this ID with KT Health Soft to get your license file</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <code className="text-2xl font-bold tracking-widest bg-gray-100 px-4 py-2 rounded-lg select-all">
                {machineInfo.machine_id}
              </code>
              <Button variant="outline" size="sm" onClick={() => {
                navigator.clipboard.writeText(machineInfo.machine_id);
                setMessage({ type: 'success', text: 'Machine ID copied to clipboard' });
                setTimeout(() => setMessage(null), 2000);
              }}>
                Copy
              </Button>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              {machineInfo.hostname} | {machineInfo.os}
            </p>
          </CardContent>
        </Card>
      )}

      {/* License Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            License Information
          </CardTitle>
          <CardDescription>Current license details and status</CardDescription>
        </CardHeader>
        <CardContent>
          {license?.status === 'no_license' ? (
            <p className="text-gray-500">No license installed. Upload a license file to activate the system.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-500">License ID</p>
                <p className="font-mono text-sm">{license?.license_id}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Hospital</p>
                <p className="font-medium">{license?.hospital_name}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Plan</p>
                <p className="font-medium capitalize">{license?.plan}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Max Users</p>
                <p className="font-medium">{license?.max_users || 'Unlimited'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Issued</p>
                <p className="font-medium">{license?.issued_at ? new Date(license.issued_at).toLocaleDateString() : '-'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Expires</p>
                <p className="font-medium">{license?.expires_at ? new Date(license.expires_at).toLocaleDateString() : '-'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Days Remaining</p>
                <p className={`font-medium ${license?.days_remaining <= 0 ? 'text-red-600' : license?.days_remaining <= 30 ? 'text-yellow-600' : 'text-green-600'}`}>
                  {license?.days_remaining > 0 ? `${license.days_remaining} days` : 'Expired'}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Features</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(license?.features || []).map(f => (
                    <Badge key={f} variant="outline" className="text-xs capitalize">{f}</Badge>
                  ))}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Status Message */}
      {license?.message && (
        <Card>
          <CardContent className="pt-6">
            <p className={`text-sm ${license.status === 'active' ? 'text-green-700' : license.status === 'expiring_soon' ? 'text-yellow-700' : 'text-red-700'}`}>
              {license.message}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Upload License — verify-before-apply flow */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload or Renew License
          </CardTitle>
          <CardDescription>
            Choose a .lic file to verify it. The license is only applied after you click Apply.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <input
              type="file"
              accept=".lic"
              onChange={handleFilePicked}
              className="hidden"
              id="license-upload"
              disabled={uploading}
            />
            <label htmlFor="license-upload">
              <Button asChild disabled={uploading}>
                <span>
                  <Upload className="h-4 w-4 mr-2" />
                  {pending?.file ? `Choose different file` : 'Choose License File'}
                </span>
              </Button>
            </label>
            {pending?.file && (
              <span className="text-sm text-gray-600">{pending.file.name}</span>
            )}
          </div>

          {pending?.checking && (
            <p className="text-sm text-muted-foreground">Verifying license…</p>
          )}

          {pending && !pending.checking && pending.inspect && (
            <div className={`rounded-lg p-4 text-sm border ${
              pending.inspect.valid_signature && pending.inspect.machine_match
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}>
              {!pending.inspect.valid_signature ? (
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold">Invalid license</div>
                    <div>{pending.inspect.error || 'Signature verification failed.'}</div>
                  </div>
                </div>
              ) : !pending.inspect.machine_match ? (
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <div className="font-semibold">License is for a different machine</div>
                    <div>
                      License is bound to{' '}
                      <code>{pending.inspect.license_machine_id}</code> but this
                      machine is <code>{pending.inspect.current_machine_id}</code>.
                    </div>
                    <div className="text-xs">
                      Use <strong>Generate Rebind Request</strong> below to ask your
                      vendor to re-issue this license for this machine.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <div className="font-semibold">License valid for this machine</div>
                      <div>{pending.inspect.hospital_name} · {pending.inspect.plan} plan</div>
                      <div>
                        Expires {pending.inspect.expires_at
                          ? new Date(pending.inspect.expires_at).toLocaleDateString()
                          : 'unknown'}
                        {' '}({pending.inspect.days_remaining} days remaining)
                      </div>
                      {(pending.inspect.features || []).length > 0 && (
                        <div className="text-xs">
                          Modules: {pending.inspect.features.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 pt-2 border-t border-green-200">
                    <Button onClick={applyPending} disabled={uploading}>
                      {uploading ? 'Applying…' : 'Apply License'}
                    </Button>
                    <Button variant="outline" onClick={() => setPending(null)} disabled={uploading}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Rebind request — only meaningful when there's an existing license */}
      {license?.license_id && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Send className="h-5 w-5" />
              Move License to This Machine
            </CardTitle>
            <CardDescription>
              Use this when you've moved the application to a new server / machine and the
              old <code>.lic</code> file is no longer accepted. Generates a request file
              your vendor can process to re-issue the license for this machine — no manual
              data entry needed on their side.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {machineInfo && license?.license_id && (
              <div className="text-xs text-gray-600 space-y-1">
                <div>Current license: <code>{license.license_id}</code></div>
                {license?.license_machine_id && (
                  <div className="flex items-center gap-1">
                    <Cpu className="w-3 h-3" />
                    Licensed machine: <code>{license.license_machine_id}</code>
                  </div>
                )}
                <div className="flex items-center gap-1">
                  <Cpu className="w-3 h-3" />
                  This machine: <code>{machineInfo.machine_id}</code>
                </div>
              </div>
            )}
            {license?.machine_match === false ? (
              <Button onClick={downloadRebindRequest} disabled={rebinding}>
                <Download className="w-4 h-4 mr-2" />
                {rebinding ? 'Generating…' : 'Generate Rebind Request'}
              </Button>
            ) : (
              <p className="text-sm text-green-700 flex items-center gap-1">
                <CheckCircle className="w-4 h-4" />
                This machine already matches the licensed machine — no rebind is needed.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default LicenseManagement;
