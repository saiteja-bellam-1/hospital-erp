import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';

const BillingModule = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900">Billing Management</h1>
      <Card>
        <CardHeader>
          <CardTitle>Billing Module</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-600">Billing management interface will be implemented here...</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default BillingModule;
