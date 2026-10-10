import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { MessageCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';

let statusRequest = null;

function loadWhatsAppEnabled() {
  if (!statusRequest) {
    statusRequest = axios.get('/api/whatsapp/status')
      .then((res) => Boolean(res.data?.enabled))
      .catch(() => false);
  }
  return statusRequest;
}

function apiErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => (typeof item === 'string' ? item : item?.msg)).filter(Boolean);
    if (parts.length) return parts.join(', ');
  }
  return fallback;
}

/**
 * Send one already-saved patient document on WhatsApp.
 * Renders nothing when the license add-on is off.
 */
export default function WhatsAppSendButton({
  kind,
  resourceId,
  phone = '',
  includeHeader,
  disabled = false,
  className = '',
  size = 'sm',
  label = 'WhatsApp',
}) {
  const [enabled, setEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [number, setNumber] = useState(phone || '');
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!kind || resourceId == null || resourceId === '') return undefined;
    let cancelled = false;
    loadWhatsAppEnabled().then((on) => {
      if (!cancelled) setEnabled(on);
    });
    return () => { cancelled = true; };
  }, [kind, resourceId]);

  useEffect(() => {
    setNumber(phone || '');
  }, [phone]);

  useEffect(() => {
    if (!open || !kind || resourceId == null || resourceId === '') return undefined;
    let cancelled = false;
    setNotice('');
    axios.get('/api/whatsapp/documents/defaults', {
      params: { kind, resource_id: String(resourceId) },
    }).then((res) => {
      if (cancelled || phone) return;
      if (res.data?.phone) setNumber(res.data.phone);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [open, kind, resourceId, phone]);

  if (!enabled || !kind || resourceId == null || resourceId === '') return null;

  const send = async () => {
    setSending(true);
    setNotice('');
    try {
      await axios.post('/api/whatsapp/documents', {
        kind,
        resource_id: String(resourceId),
        phone: number,
        ...(includeHeader === undefined ? {} : { include_header: includeHeader }),
      });
      setNotice('Sent on WhatsApp.');
      setOpen(false);
    } catch (error) {
      setNotice(apiErrorMessage(error, 'Could not send the WhatsApp message.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        size={size}
        variant="outline"
        className={className}
        disabled={disabled}
        aria-label={label || 'Send on WhatsApp'}
        title="Send on WhatsApp"
        onClick={(event) => {
          event.stopPropagation();
          setNotice('');
          setOpen(true);
        }}
      >
        <MessageCircle className={label ? 'h-3.5 w-3.5 mr-1' : 'h-3.5 w-3.5'} />
        {label || null}
      </Button>
      {notice && !open && <span className="text-xs text-gray-600">{notice}</span>}
      <Dialog open={open} onOpenChange={(next) => { if (!sending) setOpen(next); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Send on WhatsApp</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor={`wa-${kind}-${resourceId}`} className="text-xs">WhatsApp number</Label>
              <input
                id={`wa-${kind}-${resourceId}`}
                className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder="10-digit mobile"
              />
            </div>
            {notice && <p className="text-sm text-gray-700">{notice}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={sending}>
                Cancel
              </Button>
              <Button type="button" onClick={send} disabled={sending || !number.trim()}>
                {sending ? 'Sending…' : 'Send'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
