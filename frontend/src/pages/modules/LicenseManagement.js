import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Upload, Shield, CheckCircle, AlertTriangle, XCircle, Clock } from 'lucide-react';
import axios from 'axios';

const LicenseManagement = () => {
  const [license, setLicense] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [machineInfo, setMachineInfo] = useState(null);

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

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.name.endsWith('.lic')) {
      setMessage({ type: 'error', text: 'Please upload a valid .lic license file' });
      return;
    }

    setUploading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/license/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMessage({ type: 'success', text: response.data.message });
      setLicense(response.data.license);
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Failed to upload license file',
      });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const getStatusBadge = (status) => {
    const configs = {
      active: { variant: 'default', className: 'bg-green-100 text-green-800', icon: <CheckCircle className="h-3 w-3" />, label: 'Active' },
      expiring_soon: { variant: 'default', className: 'bg-yellow-100 text-yellow-800', icon: <AlertTriangle className="h-3 w-3" />, label: 'Expiring Soon' },
      grace_period: { variant: 'default', className: 'bg-red-100 text-red-800', icon: <Clock className="h-3 w-3" />, label: 'Grace Period' },
      expired: { variant: 'destructive', className: '', icon: <XCircle className="h-3 w-3" />, label: 'Expired' },
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

      {/* Upload License */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload License
          </CardTitle>
          <CardDescription>Upload a new .lic license file to activate or renew</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <input
              type="file"
              accept=".lic"
              onChange={handleFileUpload}
              className="hidden"
              id="license-upload"
              disabled={uploading}
            />
            <label htmlFor="license-upload">
              <Button asChild disabled={uploading}>
                <span>
                  <Upload className="h-4 w-4 mr-2" />
                  {uploading ? 'Uploading...' : 'Choose License File'}
                </span>
              </Button>
            </label>
            <span className="text-sm text-gray-500">Accepts .lic files only</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default LicenseManagement;
