import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import {
  Users,
  Stethoscope,
  Pill,
  Receipt,
  Calendar,
  TrendingUp,
  Activity,
} from 'lucide-react';

import { useAuth } from '../../contexts/AuthContext';

const StatCard = ({ title, value, icon, color = 'blue' }) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
      <CardTitle className="text-sm font-medium">{title}</CardTitle>
      <div className={`h-4 w-4 text-${color}-600`}>
        {icon}
      </div>
    </CardHeader>
    <CardContent>
      <div className="text-2xl font-bold">{value}</div>
    </CardContent>
  </Card>
);

const DashboardHome = () => {
  const { user } = useAuth();

  const getDashboardTitle = () => {
    switch (user.role) {
      case 'super_admin':
        return 'Super Admin Dashboard';
      case 'hospital_admin':
        return 'Hospital Administration Dashboard';
      case 'doctor':
        return 'Doctor Portal';
      case 'lab_admin':
        return 'Laboratory Management';
      case 'pharmacy_admin':
        return 'Pharmacy Management';
      case 'billing_admin':
        return 'Billing Management';
      default:
        return 'Hospital ERP Dashboard';
    }
  };

  const getStatsForRole = () => {
    // This would be populated with real data from API calls
    const baseStats = [
      { title: 'Total Patients', value: '1,234', icon: <Users className="h-4 w-4" />, color: 'blue' },
      { title: 'Today\'s Appointments', value: '56', icon: <Calendar className="h-4 w-4" />, color: 'green' },
    ];

    switch (user.role) {
      case 'super_admin':
        return [
          { title: 'Total Hospitals', value: '12', icon: <Stethoscope className="h-4 w-4" />, color: 'blue' },
          { title: 'Active Users', value: '456', icon: <Users className="h-4 w-4" />, color: 'green' },
          { title: 'System Revenue', value: '$123,456', icon: <Receipt className="h-4 w-4" />, color: 'yellow' },
          { title: 'Modules Active', value: '6', icon: <Activity className="h-4 w-4" />, color: 'purple' },
        ];
      
      case 'hospital_admin':
        return [
          ...baseStats,
          { title: 'Lab Tests Today', value: '89', icon: <Stethoscope className="h-4 w-4" />, color: 'purple' },
          { title: 'Revenue Today', value: '$12,345', icon: <Receipt className="h-4 w-4" />, color: 'yellow' },
        ];
      
      case 'doctor':
        return [
          { title: 'My Patients', value: '234', icon: <Users className="h-4 w-4" />, color: 'blue' },
          { title: 'Today\'s Appointments', value: '12', icon: <Calendar className="h-4 w-4" />, color: 'green' },
          { title: 'Pending Reports', value: '5', icon: <Stethoscope className="h-4 w-4" />, color: 'orange' },
          { title: 'Prescriptions', value: '18', icon: <Pill className="h-4 w-4" />, color: 'purple' },
        ];
      
      default:
        return baseStats;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">
          {getDashboardTitle()}
        </h1>
        <p className="mt-2 text-lg text-gray-600">
          Welcome back, {user.full_name}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {getStatsForRole().map((stat, index) => (
          <StatCard key={index} {...stat} />
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <Activity className="mr-2 h-5 w-5" />
                Recent Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-gray-600">
                Activity timeline will be displayed here...
              </p>
            </CardContent>
          </Card>
        </div>
        
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <TrendingUp className="mr-2 h-5 w-5" />
                Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-gray-600">
                Quick action buttons will be displayed here...
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default DashboardHome;