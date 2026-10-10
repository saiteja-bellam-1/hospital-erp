import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { ArrowLeft, MessageCircle, Save } from 'lucide-react';

function apiErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => (typeof item === 'string' ? item : item?.msg)).filter(Boolean);
    if (parts.length) return parts.join(', ');
  }
  return fallback;
}

const EMPTY = {
  enabled: true,
  integrated_number: '',
  public_base_url: '',
  template_invoice: '',
  template_lab_report: '',
  template_prescription: '',
  template_discharge: '',
  auth_key: '',
};

const WhatsAppSettingsPage = () => {
  const [form, setForm] = useState(EMPTY);
  const [authKeySet, setAuthKeySet] = useState(false);
  const [licensed, setLicensed] = useState(false);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    axios.get('/api/whatsapp/settings')
      .then((res) => {
        if (cancelled) return;
        const data = res.data || {};
        setLicensed(Boolean(data.licensed));
        setAuthKeySet(Boolean(data.auth_key_set));
        setRecent(data.recent || []);
        setForm({
          enabled: data.enabled !== false,
          integrated_number: data.integrated_number || '',
          public_base_url: data.public_base_url || '',
          template_invoice: data.template_invoice || '',
          template_lab_report: data.template_lab_report || '',
          template_prescription: data.template_prescription || '',
          template_discharge: data.template_discharge || '',
          auth_key: '',
        });
      })
      .catch((err) => {
        if (!cancelled) setError(apiErrorMessage(err, 'Could not load WhatsApp settings.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const setField = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    setNotice('');
    setError('');
    const payload = { ...form };
    if (!payload.auth_key) delete payload.auth_key;
    try {
      const res = await axios.put('/api/whatsapp/settings', payload);
      const data = res.data || {};
      setAuthKeySet(Boolean(data.auth_key_set));
      setRecent(data.recent || []);
      setForm((prev) => ({ ...prev, auth_key: '' }));
      setNotice('WhatsApp settings saved.');
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save WhatsApp settings.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500">Loading WhatsApp settings…</p>;
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/dashboard/home"><ArrowLeft className="h-4 w-4 mr-1" /> Back</Link>
        </Button>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <MessageCircle className="h-5 w-5" /> WhatsApp
        </h1>
      </div>

      {!licensed && (
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          This hospital's license does not include WhatsApp. Sending stays off until a license with the add-on is installed.
        </p>
      )}
      {notice && <p className="text-sm text-green-700">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">MSG91 connection</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.enabled} onChange={setField('enabled')} />
            Allow staff to send documents on WhatsApp
          </label>
          <div>
            <Label>MSG91 auth key</Label>
            <Input
              type="password"
              value={form.auth_key}
              onChange={setField('auth_key')}
              placeholder={authKeySet ? 'Saved. Enter a new key to replace it.' : 'Auth key'}
              autoComplete="new-password"
            />
          </div>
          <div>
            <Label>WhatsApp business number</Label>
            <Input value={form.integrated_number} onChange={setField('integrated_number')} placeholder="91XXXXXXXXXX" />
          </div>
          <div>
            <Label>Public base URL</Label>
            <Input
              value={form.public_base_url}
              onChange={setField('public_base_url')}
              placeholder="https://hospital.example"
            />
            <p className="text-xs text-gray-500 mt-1">
              MSG91 downloads each PDF from this address. Use the hospital's public origin, without a path.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Approved template names</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label>Invoice</Label>
            <Input value={form.template_invoice} onChange={setField('template_invoice')} />
          </div>
          <div>
            <Label>Lab report</Label>
            <Input value={form.template_lab_report} onChange={setField('template_lab_report')} />
          </div>
          <div>
            <Label>Prescription</Label>
            <Input value={form.template_prescription} onChange={setField('template_prescription')} />
          </div>
          <div>
            <Label>Discharge summary</Label>
            <Input value={form.template_discharge} onChange={setField('template_discharge')} />
          </div>
          <p className="text-xs text-gray-500 sm:col-span-2">
            Create these in MSG91 as Utility templates with a document header and four body variables:
            patient name, reference, hospital name, and date. Prescription and discharge names can be saved now and used when those documents are connected.
          </p>
        </CardContent>
      </Card>

      <Button onClick={save} disabled={saving || !licensed}>
        <Save className="h-4 w-4 mr-2" /> {saving ? 'Saving…' : 'Save'}
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent sends</CardTitle>
        </CardHeader>
        <CardContent>
          {recent.length === 0 ? (
            <p className="text-sm text-gray-500">No WhatsApp messages yet.</p>
          ) : (
            <ul className="text-sm divide-y">
              {recent.map((row) => (
                <li key={row.id} className="py-2 flex justify-between gap-3">
                  <span>
                    {row.resource_type} {row.resource_id} · {row.phone}
                  </span>
                  <span className={row.status === 'failed' ? 'text-red-600' : 'text-gray-600'}>
                    {row.status}{row.error ? ` — ${row.error}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default WhatsAppSettingsPage;
