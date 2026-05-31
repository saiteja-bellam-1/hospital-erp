import React, { useState } from 'react';
import { Button } from '../../../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import {
  Upload,
  Download,
  CheckCircle2,
  XCircle,
  Loader2,
  Users,
  Stethoscope,
  HeartPulse,
} from 'lucide-react';
import axios from 'axios';

const ROLE_META = {
  doctor: {
    label: 'Doctors',
    icon: Stethoscope,
    description:
      'Required: username, email, first_name, last_name, password, specialization, license_number. ' +
      'Optional: phone, qualification, consultation_fee_inr, inpatient_fee_inr, emergency_fee_inr, ' +
      'experience_years, default_consultation_duration.',
    endpoint: '/api/admin/users/bulk-import-doctors',
    sampleFile: 'doctors_sample.csv',
  },
  nurse: {
    label: 'Nurses',
    icon: HeartPulse,
    description:
      'Required: username, email, first_name, last_name, password. Optional: phone.',
    endpoint: '/api/admin/users/bulk-import-nurses',
    sampleFile: 'nurses_sample.csv',
  },
};

const BulkUserImportDialog = ({ open, onOpenChange, onImported }) => {
  const { toast } = useToast();
  const [role, setRole] = useState('doctor');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const meta = ROLE_META[role];

  const resetState = () => {
    setFile(null);
    setResult(null);
    const input = document.getElementById('bulk-import-file');
    if (input) input.value = '';
  };

  const handleDownloadSample = async () => {
    // Use axios so the JWT token (set globally on axios.defaults.headers) is
    // sent. A plain <a href> would get a 401 and show a blank page.
    try {
      const { data } = await axios.get(
        `/api/admin/users/bulk-import-sample/${role}`,
        { responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(new Blob([data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = meta.sampleFile;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast({
        title: 'Could not download sample',
        description: err.message,
        variant: 'destructive',
      });
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast({ title: 'Pick a CSV file first', variant: 'destructive' });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const { data } = await axios.post(meta.endpoint, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(data);
      if (data.ok) {
        toast({
          title: `${meta.label} imported`,
          description: `Created ${data.created} user(s). Each must change their password on first login.`,
        });
        setFile(null);
        const input = document.getElementById('bulk-import-file');
        if (input) input.value = '';
        if (onImported) onImported();
      } else {
        toast({
          title: 'Import rejected',
          description: `Fix ${data.errors.length} row error(s) and try again — no users were created.`,
          variant: 'destructive',
        });
      }
    } catch (err) {
      const detail =
        typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : err.message;
      toast({ title: 'Upload failed', description: detail, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const Icon = meta.icon;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) resetState();
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center">
            <Users className="h-5 w-5 mr-2" />
            Bulk import users
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Role picker */}
          <div className="flex gap-2">
            {Object.entries(ROLE_META).map(([key, m]) => {
              const RoleIcon = m.icon;
              return (
                <Button
                  key={key}
                  variant={role === key ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    setRole(key);
                    resetState();
                  }}
                >
                  <RoleIcon className="h-4 w-4 mr-2" />
                  {m.label}
                </Button>
              );
            })}
          </div>

          {/* Format hint */}
          <div className="rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900 flex items-start gap-2">
            <Icon className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-medium mb-1">{meta.label} CSV format</div>
              <div className="text-xs leading-relaxed">{meta.description}</div>
              <div className="text-xs mt-1 text-blue-800">
                Passwords are hashed before storage. Every imported user is forced to
                change their password on first login.
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadSample}>
              <Download className="h-4 w-4 mr-2" />
              Download sample CSV
            </Button>

            <label className="inline-flex items-center cursor-pointer">
              <input
                id="bulk-import-file"
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setResult(null);
                }}
              />
              <Button variant="outline" size="sm" asChild>
                <span>
                  <Upload className="h-4 w-4 mr-2" />
                  {file ? file.name : 'Choose CSV...'}
                </span>
              </Button>
            </label>
          </div>

          {/* Result */}
          {result && result.ok && (
            <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="h-4 w-4" />
                Created {result.created} {meta.label.toLowerCase()}.
              </div>
              {result.usernames?.length > 0 && (
                <div className="mt-2 text-xs">
                  Usernames: {result.usernames.join(', ')}
                </div>
              )}
            </div>
          )}

          {result && !result.ok && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              <div className="flex items-center gap-2 font-medium mb-2">
                <XCircle className="h-4 w-4" />
                No users were created — fix these row errors and try again:
              </div>
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-red-200 text-left">
                      <th className="py-1 pr-2 w-16">Line</th>
                      <th className="py-1 pr-2 w-40">Field</th>
                      <th className="py-1">Problem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.map((e, i) => (
                      <tr key={i} className="border-b border-red-100 last:border-0">
                        <td className="py-1 pr-2 font-mono">{e.line ?? '—'}</td>
                        <td className="py-1 pr-2 font-mono">{e.field ?? '—'}</td>
                        <td className="py-1">{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button onClick={handleUpload} disabled={!file || busy}>
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Uploading...
              </>
            ) : (
              <>Import {meta.label.toLowerCase()}</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BulkUserImportDialog;
