import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Save, Upload, X } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import axios from 'axios';

const COMMON_FIELDS = [
  { key: 'provider_name', label: 'Provider / Lab Name', placeholder: 'ABC Diagnostics Pvt. Ltd.' },
  { key: 'provider_address', label: 'Address', placeholder: '123, MG Road' },
  { key: 'provider_city', label: 'City', placeholder: 'Hyderabad' },
  { key: 'provider_state', label: 'State', placeholder: 'Telangana' },
  { key: 'provider_pincode', label: 'Pincode', placeholder: '500001' },
  { key: 'provider_phone', label: 'Phone', placeholder: '+91-9876543210' },
  { key: 'provider_email', label: 'Email', placeholder: 'info@abcdiagnostics.com' },
];

const REGISTRATION_FIELDS = [
  { key: 'registration_number', label: 'Registration Number', placeholder: 'REG-2024-001' },
  { key: 'nabl_number', label: 'NABL Accreditation Number', placeholder: 'NABL-MC-1234' },
  { key: 'license_number', label: 'License Number', placeholder: 'LIC-2024-001' },
];

const SIGNATORY_FIELDS = [
  { key: 'pathologist_name', label: 'Pathologist / Signatory Name', placeholder: 'Dr. John Smith' },
  { key: 'pathologist_qualification', label: 'Qualification', placeholder: 'MD Pathology, DMLT' },
];

const PHARMACY_EXTRA_FIELDS = [
  { key: 'drug_license_number', label: 'Drug License Number', placeholder: 'DL-20B-12345' },
  { key: 'pharmacist_name', label: 'Pharmacist Name', placeholder: 'Mr. Rajesh Kumar' },
  { key: 'gst_number', label: 'GST Number', placeholder: '36AABCU9603R1ZM' },
];

// Provider identity fields — only relevant when the lab/pharmacy is a third party.
// For in-house, these are left empty so reports fall back to the hospital's own details.
const PROVIDER_FIELD_KEYS = [
  ...COMMON_FIELDS.map(f => f.key),
  'provider_logo',
];

const ImageUploadField = ({ label, configKey, value, onChange }) => {
  const [uploading, setUploading] = useState(false);
  const { toast } = useToast();

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      toast({ variant: 'destructive', title: 'Error', description: 'File must be under 2MB' });
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/hospital/upload-file', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onChange(configKey, response.data.url);
      toast({ title: 'Uploaded', description: `${label} uploaded successfully` });
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: error.response?.data?.detail || 'Upload failed' });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex items-center gap-3">
        {value ? (
          <div className="relative">
            <img
              src={`${value}`}
              alt={label}
              className="h-16 w-auto border rounded object-contain bg-white"
            />
            <button
              type="button"
              onClick={() => onChange(configKey, '')}
              className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div className="h-16 w-24 border-2 border-dashed rounded flex items-center justify-center text-gray-400 text-xs">
            No image
          </div>
        )}
        <div>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={handleUpload}
            className="hidden"
            id={`upload-${configKey}`}
            disabled={uploading}
          />
          <label htmlFor={`upload-${configKey}`}>
            <Button asChild size="sm" variant="outline" disabled={uploading}>
              <span>
                <Upload className="h-3 w-3 mr-1" />
                {uploading ? 'Uploading...' : 'Upload'}
              </span>
            </Button>
          </label>
        </div>
      </div>
    </div>
  );
};

const ModuleConfigForm = ({ moduleName }) => {
  const [config, setConfig] = useState({});
  const [providerType, setProviderType] = useState('in_house');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const isPharmacy = moduleName === 'pharmacy';
  const moduleLabel = isPharmacy ? 'Pharmacy' : 'Laboratory';
  const isThirdParty = providerType === 'third_party';

  useEffect(() => {
    fetchConfig();
  }, [moduleName]);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/api/hospital/module-config/${moduleName}`);
      const loaded = response.data.config || {};
      setConfig(loaded);
      // Infer the mode from stored data: a provider name means it's an external
      // third party; otherwise the lab/pharmacy is run by the hospital itself.
      setProviderType((loaded.provider_name || '').trim() ? 'third_party' : 'in_house');
    } catch (error) {
      console.error('Failed to fetch module config:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  const handleProviderTypeChange = (type) => {
    setProviderType(type);
    // Switching to in-house clears the provider identity fields so reports fall
    // back to the hospital's own name/address/logo.
    if (type === 'in_house') {
      setConfig(prev => {
        const next = { ...prev };
        PROVIDER_FIELD_KEYS.forEach(k => { next[k] = ''; });
        return next;
      });
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (isThirdParty && !(config.provider_name || '').trim()) {
      toast({ variant: 'destructive', title: 'Missing name', description: `Enter the third-party ${moduleLabel.toLowerCase()} name` });
      return;
    }
    setSaving(true);
    try {
      await axios.put(`/api/hospital/module-config/${moduleName}`, { config });
      toast({ title: 'Saved', description: `${moduleLabel} configuration saved successfully` });
    } catch (error) {
      toast({ variant: 'destructive', title: 'Error', description: error.response?.data?.detail || 'Failed to save' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8 text-gray-500">Loading configuration...</div>;
  }

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Ownership toggle */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{moduleLabel} Ownership</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {[
              { id: 'in_house', label: 'In-house', hint: `Run by the hospital itself` },
              { id: 'third_party', label: 'Third-party', hint: `Operated by an external provider` },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => handleProviderTypeChange(opt.id)}
                className={`px-4 py-2 rounded-md border text-sm text-left ${
                  providerType === opt.id
                    ? 'border-primary bg-primary/10 text-primary font-medium'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div>{opt.label}</div>
                <div className="text-xs text-gray-500 font-normal">{opt.hint}</div>
              </button>
            ))}
          </div>
          {!isThirdParty && (
            <p className="text-xs text-gray-500">
              The hospital's own name, address, and logo will be used on {moduleLabel.toLowerCase()} reports.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Provider Info — only for third-party */}
      {isThirdParty && (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isPharmacy ? 'Pharmacy' : 'Lab'} Service Provider Details
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {COMMON_FIELDS.map(f => (
              <div key={f.key}>
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  value={config[f.key] || ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
          </div>
          <ImageUploadField
            label="Provider Logo"
            configKey="provider_logo"
            value={config.provider_logo || ''}
            onChange={handleChange}
          />
        </CardContent>
      </Card>
      )}

      {/* Registration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Registration & License</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {REGISTRATION_FIELDS.map(f => (
              <div key={f.key}>
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  value={config[f.key] || ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
            {isPharmacy && PHARMACY_EXTRA_FIELDS.map(f => (
              <div key={f.key}>
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  value={config[f.key] || ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Signatory */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Signatory Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SIGNATORY_FIELDS.map(f => (
              <div key={f.key}>
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  value={config[f.key] || ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
          </div>
          <ImageUploadField
            label="Signature Image"
            configKey="signature_image"
            value={config.signature_image || ''}
            onChange={handleChange}
          />
        </CardContent>
      </Card>

      <Button type="submit" disabled={saving}>
        <Save className="h-4 w-4 mr-2" />
        {saving ? 'Saving...' : `Save ${moduleLabel} Configuration`}
      </Button>
    </form>
  );
};

export default ModuleConfigForm;
