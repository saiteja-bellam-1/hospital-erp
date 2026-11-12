import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Phone, MapPin, Building2, Mail } from 'lucide-react';
import { phoneTel } from '../../utils/supportContact';

const SupportContactPage = ({ contact }) => {
  const [logoFailed, setLogoFailed] = useState(false);

  useEffect(() => {
    setLogoFailed(false);
  }, [contact?.logo_url]);

  if (!contact?.name) {
    return (
      <div className="text-center py-20 text-gray-500">
        <Phone className="h-10 w-10 mx-auto mb-3 text-gray-300" />
        <p>No support contact on this license.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold">Support Contact</h1>
        <p className="text-muted-foreground text-sm">Who to call for this installation</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-blue-600" />
            {contact.name}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {contact.logo_url && !logoFailed && (
            <img
              src={contact.logo_url}
              alt=""
              className="max-h-16 max-w-[220px] object-contain"
              onError={() => setLogoFailed(true)}
            />
          )}
          {contact.address && (
            <div className="flex items-start gap-3">
              <MapPin className="h-5 w-5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs text-gray-500 font-medium">Address</p>
                <p className="text-sm">{contact.address}</p>
              </div>
            </div>
          )}
          {contact.phone && (
            <div className="flex items-start gap-3">
              <Phone className="h-5 w-5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs text-gray-500 font-medium">Contact Number</p>
                <a href={phoneTel(contact.phone)} className="text-sm font-medium text-primary hover:underline">{contact.phone}</a>
              </div>
            </div>
          )}
          {contact.email && (
            <div className="flex items-start gap-3">
              <Mail className="h-5 w-5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs text-gray-500 font-medium">Email</p>
                <a href={`mailto:${contact.email}`} className="text-sm font-medium text-primary hover:underline">{contact.email}</a>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default SupportContactPage;
