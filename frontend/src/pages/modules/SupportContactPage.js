import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Phone, MapPin, Building2 } from 'lucide-react';

const SupportContactPage = ({ sellerInfo }) => {
  if (!sellerInfo) {
    return (
      <div className="text-center py-20 text-gray-500">
        <Phone className="h-10 w-10 mx-auto mb-3 text-gray-300" />
        <p>No vendor contact information available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold">Support Contact</h1>
        <p className="text-muted-foreground text-sm">Your software vendor details</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-blue-600" />
            {sellerInfo.name}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sellerInfo.address && (
            <div className="flex items-start gap-3">
              <MapPin className="h-5 w-5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs text-gray-500 font-medium">Address</p>
                <p className="text-sm">{sellerInfo.address}</p>
              </div>
            </div>
          )}
          {sellerInfo.phone && (
            <div className="flex items-start gap-3">
              <Phone className="h-5 w-5 text-gray-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs text-gray-500 font-medium">Contact Number</p>
                <p className="text-sm font-medium">{sellerInfo.phone}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default SupportContactPage;
