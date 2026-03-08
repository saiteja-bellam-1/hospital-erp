import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';

const InpatientModule = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900">Inpatient Management</h1>
      <Card>
        <CardHeader>
          <CardTitle>Inpatient Module</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-600">Inpatient management interface will be implemented here...</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default InpatientModule;
