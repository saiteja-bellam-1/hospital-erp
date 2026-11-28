import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { useToast } from '../hooks/use-toast';
import { MessageCircle, Paperclip, Plus, X, FileText, Image as ImageIcon } from 'lucide-react';

const MAX_FILES = 5;
const MAX_BYTES = 15 * 1024 * 1024;
const ACCEPT = 'application/pdf,image/png,image/jpeg';

const errText = (e) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : 'Could not send WhatsApp message';
};

const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/**
 * Send a WhatsApp message to a patient, with removable / addable attachments.
 *
 * Props:
 *   open, onClose
 *   kind         template key (consultation_confirmation | lab_order_confirmation | lab_report |
 *                prescription | consultation_invoice | lab_invoice | pharmacy_invoice | custom)
 *   phone        prefilled number (editable)
 *   patientName, patientId, context  — template placeholders / audit
 *   getFile      optional async () => Blob  — the document PDF, attached by default but removable
 *   filename     name of that document
 */
const WhatsAppSendDialog = ({
  open, onClose, kind = 'custom', phone = '', patientName = '', patientId = null,
  context = null, getFile = null, filename = 'document.pdf',
}) => {
  const { toast } = useToast();
  const fileInput = useRef(null);
  const [number, setNumber] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  // { id, name, size?, file?: File, document?: true }
  const [attachments, setAttachments] = useState([]);

  useEffect(() => {
    if (!open) return undefined;
    setNumber(phone || '');
    setAttachments(getFile ? [{ id: 'document', name: filename, document: true }] : []);
    let cancelled = false;
    axios.get('/api/whatsapp/templates/preview', { params: { kind, patient_name: patientName } })
      .then((r) => { if (!cancelled) setMessage(r.data.message || ''); })
      .catch(() => { if (!cancelled) setMessage(''); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kind, phone, patientName]);

  const addFiles = (list) => {
    const incoming = Array.from(list || []);
    if (!incoming.length) return;
    setAttachments((prev) => {
      const next = [...prev];
      for (const f of incoming) {
        if (next.length >= MAX_FILES) {
          toast({ title: 'Too many attachments', description: `At most ${MAX_FILES} per message`, variant: 'destructive' });
          break;
        }
        if (!ACCEPT.split(',').includes(f.type)) {
          toast({ title: 'Unsupported file', description: `${f.name}: only PDF, PNG or JPEG`, variant: 'destructive' });
          continue;
        }
        if (f.size > MAX_BYTES) {
          toast({ title: 'File too large', description: `${f.name} is over 15 MB`, variant: 'destructive' });
          continue;
        }
        next.push({ id: `${f.name}-${f.size}-${Date.now()}-${next.length}`, name: f.name, size: f.size, file: f });
      }
      return next;
    });
    if (fileInput.current) fileInput.current.value = '';
  };

  const removeAttachment = (id) => setAttachments((prev) => prev.filter((a) => a.id !== id));

  const send = async () => {
    setSending(true);
    try {
      const form = new FormData();
      form.append('phone', number);
      form.append('kind', kind);
      form.append('message', message);
      form.append('patient_name', patientName || '');
      if (patientId) form.append('patient_id', String(patientId));
      if (context) form.append('context', JSON.stringify(context));
      for (const a of attachments) {
        if (a.document) {
          const blob = await getFile();
          if (!blob) throw new Error('no-file');
          form.append('files', new File([blob], a.name, { type: blob.type || 'application/pdf' }));
        } else {
          form.append('files', a.file, a.name);
        }
      }
      await axios.post('/api/whatsapp/send', form);
      toast({ title: 'Sent on WhatsApp', description: `Message delivered to ${number}` });
      onClose && onClose();
    } catch (e) {
      toast({ title: 'WhatsApp failed', description: e.message === 'no-file' ? 'PDF is not ready yet' : errText(e), variant: 'destructive' });
    } finally {
      setSending(false);
    }
  };

  const canSend = !sending && number.trim() && (message.trim() || attachments.length > 0);

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !sending) onClose && onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-green-600" /> Send on WhatsApp
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="wa-number">
              Mobile number{patientName ? <span className="font-normal text-muted-foreground"> — {patientName}</span> : null}
            </Label>
            <Input id="wa-number" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="98765 43210" />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="wa-message">Message</Label>
            <Textarea id="wa-message" rows={5} value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="flex items-center gap-1.5">
                <Paperclip className="h-3.5 w-3.5" /> Attachments
                <span className="font-normal text-muted-foreground">({attachments.length}/{MAX_FILES})</span>
              </Label>
              <Button
                type="button" size="sm" variant="outline" className="h-7 px-2 text-xs"
                disabled={sending || attachments.length >= MAX_FILES}
                onClick={() => fileInput.current?.click()}
              >
                <Plus className="h-3.5 w-3.5 mr-1" /> Add file
              </Button>
              <input ref={fileInput} type="file" accept={ACCEPT} multiple hidden onChange={(e) => addFiles(e.target.files)} />
            </div>

            {attachments.length === 0 ? (
              <p className="rounded-md border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
                No attachments — only the message text will be sent.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {attachments.map((a) => (
                  <li key={a.id} className="flex items-center gap-2 rounded-md border bg-gray-50 px-2.5 py-1.5">
                    {/\.(png|jpe?g)$/i.test(a.name)
                      ? <ImageIcon className="h-4 w-4 shrink-0 text-gray-500" />
                      : <FileText className="h-4 w-4 shrink-0 text-red-500" />}
                    <span className="min-w-0 flex-1 truncate text-sm" title={a.name}>{a.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {a.document ? 'Document' : fmtSize(a.size)}
                    </span>
                    <button
                      type="button" aria-label={`Remove ${a.name}`} disabled={sending}
                      className="shrink-0 rounded p-0.5 text-gray-500 hover:bg-gray-200 hover:text-red-600 disabled:opacity-50"
                      onClick={() => removeAttachment(a.id)}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex gap-3 pt-1">
            <Button variant="outline" className="flex-1" onClick={onClose} disabled={sending}>Cancel</Button>
            <Button className="flex-1 bg-green-600 hover:bg-green-700" onClick={send} disabled={!canSend}>
              {sending ? 'Sending…' : 'Send'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default WhatsAppSendDialog;
