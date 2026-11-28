import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { useToast } from '../../../hooks/use-toast';
import { MessageCircle } from 'lucide-react';

const KIND_LABELS = {
  consultation_confirmation: 'Consultation confirmation',
  lab_order_confirmation: 'Lab order confirmation',
  lab_report: 'Lab report',
  prescription: 'Prescription',
  consultation_invoice: 'Consultation invoice',
  lab_invoice: 'Lab invoice',
  pharmacy_invoice: 'Pharmacy invoice',
};

const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
};

const STATE_TEXT = {
  disabled: 'Disabled',
  stopped: 'Service not running',
  starting: 'Starting…',
  connecting: 'Connecting…',
  qr: 'Waiting for QR scan',
  connected: 'Connected',
  loggedout: 'Logged out — rescan to relink',
  unavailable: 'Unavailable',
};

const WhatsAppSettings = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState(null);
  const [conn, setConn] = useState({ state: 'disabled' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setSettings((await axios.get('/api/whatsapp/settings')).data);
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to load WhatsApp settings'), variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // Poll connection while enabled (QR refreshes every ~20 s on the WhatsApp side).
  useEffect(() => {
    if (!settings?.enabled) { setConn({ state: 'disabled' }); return undefined; }
    let stop = false;
    const tick = async () => {
      try {
        const r = await axios.get('/api/whatsapp/connection');
        if (!stop) setConn(r.data);
      } catch { /* keep last state */ }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { stop = true; clearInterval(id); };
  }, [settings?.enabled]);

  const save = async (patch, okMsg) => {
    setSaving(true);
    try {
      const r = await axios.put('/api/whatsapp/settings', patch);
      setSettings(r.data);
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] });
      toast({ title: okMsg || 'Saved' });
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to save'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const unlink = async () => {
    try {
      await axios.post('/api/whatsapp/logout');
      toast({ title: 'WhatsApp unlinked' });
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] });
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to unlink'), variant: 'destructive' });
    }
  };

  if (!settings) return <p className="text-sm text-gray-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-green-600" /> WhatsApp messaging
          </CardTitle>
          <p className="text-sm text-gray-500 mt-1">
            Send confirmations, invoices, prescriptions and lab reports to patients from the hospital&apos;s own
            WhatsApp number using WhatsApp Web. Staff trigger each message; nothing is sent automatically.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={settings.enabled}
              disabled={saving}
              onChange={(e) => save({ enabled: e.target.checked }, e.target.checked ? 'WhatsApp enabled' : 'WhatsApp disabled')}
            />
            <span className="font-medium">Enable WhatsApp messaging</span>
          </label>
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
            This uses an unofficial WhatsApp Web connection. Keep to one-to-one, staff-initiated messages to
            patients — bulk or unsolicited messaging can get the number banned by WhatsApp.
          </p>

          {settings.enabled && (
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">Connection: {STATE_TEXT[conn.state] || conn.state}</div>
                  {conn.phone && <div className="text-xs text-gray-500">Linked number: +{conn.phone}</div>}
                  {conn.message && <div className="text-xs text-red-600">{conn.message}</div>}
                </div>
                {conn.state === 'connected' && (
                  <Button variant="outline" onClick={unlink}>Unlink</Button>
                )}
              </div>
              {conn.state === 'qr' && conn.qr && (
                <div className="flex flex-col items-center gap-2">
                  <img src={conn.qr} alt="WhatsApp QR code" className="h-56 w-56 border rounded" />
                  <p className="text-xs text-gray-500 text-center">
                    On the hospital phone: WhatsApp → Settings → Linked devices → Link a device, then scan.
                  </p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Messages</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="max-w-xs">
            <Label htmlFor="wa-cc">Default country code</Label>
            <Input
              id="wa-cc"
              value={settings.default_country_code}
              onChange={(e) => setSettings({ ...settings, default_country_code: e.target.value })}
            />
            <p className="text-xs text-gray-500 mt-1">Added to 10-digit numbers (91 for India).</p>
          </div>
          {Object.entries(KIND_LABELS).map(([kind, label]) => (
            <div key={kind}>
              <Label htmlFor={`wa-t-${kind}`}>{label}</Label>
              <Textarea
                id={`wa-t-${kind}`}
                rows={3}
                value={settings.templates[kind] || ''}
                onChange={(e) => setSettings({ ...settings, templates: { ...settings.templates, [kind]: e.target.value } })}
              />
            </div>
          ))}
          <p className="text-xs text-gray-500">
            Placeholders: {'{patient_name}'} {'{hospital_name}'} {'{doctor_name}'} {'{date}'} {'{time}'} {'{order_number}'}.
            Staff can still edit the text before each send.
          </p>
          <div className="flex gap-2">
            <Button
              disabled={saving}
              onClick={() => save({ default_country_code: settings.default_country_code, templates: settings.templates }, 'Messages saved')}
            >
              Save messages
            </Button>
            <Button variant="outline" onClick={() => setSettings({ ...settings, templates: { ...settings.default_templates } })}>
              Reset to defaults
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default WhatsAppSettings;
