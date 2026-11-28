import React, { useState } from 'react';
import axios from 'axios';
import { Button } from './ui/button';
import { MessageCircle } from 'lucide-react';
import WhatsAppSendDialog from './WhatsAppSendDialog';
import useWhatsAppStatus from '../hooks/useWhatsAppStatus';

/**
 * Drop-in "WhatsApp" button for places that print a PDF without a preview dialog.
 * Renders nothing unless the admin enabled WhatsApp and the number is linked.
 * Attach with `blobUrl` (already-fetched PDF) or `pdfPath` (API path); omit both for a
 * text-only message (confirmations).
 */
const WhatsAppPdfButton = ({
  kind, phone, patientName, patientId, context, pdfPath, pdfParams, blobUrl, filename = 'document.pdf',
  label = 'WhatsApp', size = 'sm', variant = 'outline', className = '',
}) => {
  const { available } = useWhatsAppStatus();
  const [open, setOpen] = useState(false);
  if (!available) return null;
  return (
    <>
      <Button type="button" size={size} variant={variant} className={`text-green-700 border-green-300 hover:bg-green-50 ${className}`} onClick={() => setOpen(true)}>
        <MessageCircle className="h-4 w-4 shrink-0" />{label && <span className="ml-1.5 hidden sm:inline">{label}</span>}
      </Button>
      <WhatsAppSendDialog
        open={open}
        onClose={() => setOpen(false)}
        kind={kind}
        phone={phone}
        patientName={patientName}
        patientId={patientId}
        context={context}
        filename={filename}
        getFile={blobUrl
          ? async () => (await fetch(blobUrl)).blob()
          : pdfPath ? async () => (await axios.get(pdfPath, { params: pdfParams, responseType: 'blob' })).data : null}
      />
    </>
  );
};

export default WhatsAppPdfButton;
