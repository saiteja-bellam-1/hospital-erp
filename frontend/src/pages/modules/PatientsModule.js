import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Users, UserPlus, Search, FileText } from 'lucide-react';

const PatientsModule = () => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Patient Management</h1>
        <Button className="flex items-center">
          <UserPlus className="mr-2 h-4 w-4" />
          Add New Patient
        </Button>
      </div>
      
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Users className="mr-2 h-5 w-5" />
              Patient Registration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 mb-4">
              Register new patients and manage their basic information.
            </p>
            <Button variant="outline" className="w-full">
              Open Registration
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Search className="mr-2 h-5 w-5" />
              Patient Search
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 mb-4">
              Search and view existing patient records.
            </p>
            <Button variant="outline" className="w-full">
              Search Patients
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <FileText className="mr-2 h-5 w-5" />
              Medical Records
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 mb-4">
              Access and manage patient medical histories.
            </p>
            <Button variant="outline" className="w-full">
              View Records
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Patients</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-600">
            Recent patient list and quick actions will be displayed here...
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default PatientsModule;