import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import {
  Users,
  Calendar,
  Clock,
  CheckCircle,
  AlertCircle,
  TrendingUp,
  UserPlus,
  CalendarPlus,
  Activity,
  TestTube,
  Printer,
  Receipt,
  FileText,
  RefreshCw,
  Eye
} from 'lucide-react';

const ReceptionDashboard = () => {
  const [stats, setStats] = useState({
    todayAppointments: 0,
    pendingAppointments: 0,
    completedAppointments: 0,
    totalPatients: 0,
    newPatientsToday: 0
  });
  const [todayAppointments, setTodayAppointments] = useState([]);
  const [labOrders, setLabOrders] = useState([]);
  const [recentPrescriptions, setRecentPrescriptions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Dialog states
  const [showBillDialog, setShowBillDialog] = useState(false);
  const [billPdfUrl, setBillPdfUrl] = useState(null);
  const [billData, setBillData] = useState(null);
  const [showPrescriptionDialog, setShowPrescriptionDialog] = useState(false);
  const [prescriptionPdfUrl, setPrescriptionPdfUrl] = useState(null);
  const [prescriptionData, setPrescriptionData] = useState(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const today = new Date().toISOString().split('T')[0];
      
      // Fetch today's appointments
      const appointmentsResponse = await fetch(`/api/appointments/?date_from=${today}&date_to=${today}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (appointmentsResponse.ok) {
        const appointments = await appointmentsResponse.json();
        setTodayAppointments(Array.isArray(appointments) ? appointments.slice(0, 5) : []);
        
        // Calculate stats from appointments
        const todayCount = appointments.length;
        const pendingCount = appointments.filter(apt => apt.status === 'scheduled').length;
        const completedCount = appointments.filter(apt => apt.status === 'completed').length;
        
        setStats(prev => ({
          ...prev,
          todayAppointments: todayCount,
          pendingAppointments: pendingCount,
          completedAppointments: completedCount
        }));
      }
      
      // Fetch patients count
      const patientsResponse = await fetch('/api/patients/search', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          search_term: '',
          sort_by: 'name',
          sort_order: 'asc'
        })
      });

      if (patientsResponse.ok) {
        const patientsData = await patientsResponse.json();
        const patients = Array.isArray(patientsData.patients) ? patientsData.patients : [];

        setStats(prev => ({
          ...prev,
          totalPatients: patients.length,
          newPatientsToday: patients.filter(p => {
            const createdDate = new Date(p.created_at).toDateString();
            const todayDate = new Date().toDateString();
            return createdDate === todayDate;
          }).length
        }));
      }

      // Fetch today's lab orders
      try {
        const labResponse = await fetch(`/api/lab/orders?date_from=${today}&date_to=${today}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (labResponse.ok) {
          const labData = await labResponse.json();
          setLabOrders(Array.isArray(labData) ? labData : []);
        }
      } catch (e) {
        console.error('Error fetching lab orders:', e);
      }

      // Fetch recent prescriptions
      try {
        const rxResponse = await fetch('/api/prescriptions-simple/?limit=10', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (rxResponse.ok) {
          const rxData = await rxResponse.json();
          setRecentPrescriptions(Array.isArray(rxData) ? rxData : []);
        }
      } catch (e) {
        console.error('Error fetching prescriptions:', e);
      }

    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Bill preview for lab orders
  const showLabBillPreview = async (order) => {
    try {
      const token = localStorage.getItem('token');
      // If the order has a consultation_id, use consultation bill endpoint
      if (order.consultation_id) {
        const billResponse = await fetch(`/api/consultations/${order.consultation_id}/bill`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (billResponse.ok) {
          const data = await billResponse.json();
          setBillData(data);
          const pdfResponse = await fetch(`/api/consultations/${order.consultation_id}/bill/download`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (pdfResponse.ok) {
            const blob = await pdfResponse.blob();
            setBillPdfUrl(window.URL.createObjectURL(blob));
            setShowBillDialog(true);
          }
        }
      } else {
        // Show basic order info as bill
        setBillData({
          bill_number: order.order_number,
          patient_name: order.patient_name,
          doctor_name: order.doctor_name,
          total_amount: 0,
          items: [{ item_name: order.test_name, quantity: 1 }]
        });
        setShowBillDialog(true);
      }
    } catch (error) {
      console.error('Error fetching lab bill:', error);
      alert('Failed to load bill');
    }
  };

  const printBill = () => {
    if (billPdfUrl) {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
      iframe.src = billPdfUrl;
      iframe.onload = () => {
        iframe.contentWindow.print();
        setTimeout(() => document.body.removeChild(iframe), 1000);
      };
    }
  };

  const closeBillDialog = () => {
    setShowBillDialog(false);
    if (billPdfUrl) {
      window.URL.revokeObjectURL(billPdfUrl);
      setBillPdfUrl(null);
    }
    setBillData(null);
  };

  // Prescription preview
  const showPrescriptionPreview = async (prescription) => {
    try {
      const token = localStorage.getItem('token');
      setPrescriptionData(prescription);
      const pdfResponse = await fetch(`/api/prescriptions-simple/${prescription.prescription_id}/download?include_header=true`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (pdfResponse.ok) {
        const blob = await pdfResponse.blob();
        setPrescriptionPdfUrl(window.URL.createObjectURL(blob));
        setShowPrescriptionDialog(true);
      } else {
        alert('Failed to load prescription PDF');
      }
    } catch (error) {
      console.error('Error fetching prescription:', error);
      alert('Error loading prescription');
    }
  };

  const printPrescription = () => {
    if (prescriptionPdfUrl) {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
      iframe.src = prescriptionPdfUrl;
      iframe.onload = () => {
        iframe.contentWindow.print();
        setTimeout(() => document.body.removeChild(iframe), 1000);
      };
    }
  };

  const closePrescriptionDialog = () => {
    setShowPrescriptionDialog(false);
    if (prescriptionPdfUrl) {
      window.URL.revokeObjectURL(prescriptionPdfUrl);
      setPrescriptionPdfUrl(null);
    }
    setPrescriptionData(null);
  };

  const getLabStatusColor = (status) => {
    const colors = {
      'ordered': 'bg-blue-100 text-blue-800',
      'collected': 'bg-yellow-100 text-yellow-800',
      'processing': 'bg-orange-100 text-orange-800',
      'completed': 'bg-green-100 text-green-800',
      'cancelled': 'bg-red-100 text-red-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getStatusBadge = (status) => {
    const colors = {
      'scheduled': 'bg-blue-100 text-blue-800',
      'confirmed': 'bg-green-100 text-green-800',
      'in_progress': 'bg-yellow-100 text-yellow-800',
      'completed': 'bg-gray-100 text-gray-800',
      'cancelled': 'bg-red-100 text-red-800',
      'no_show': 'bg-red-100 text-red-800'
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6">
                <div className="h-8 bg-gray-200 rounded mb-2"></div>
                <div className="h-6 bg-gray-200 rounded"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Reception Dashboard</h1>
          <p className="text-gray-600">Welcome to the reception management center</p>
        </div>
        <div className="flex space-x-3">
          <Link to="/dashboard/reception/patients">
            <Button className="flex items-center space-x-2">
              <UserPlus className="h-4 w-4" />
              <span>Manage Patients</span>
            </Button>
          </Link>
          <Link to="/dashboard/reception/appointments">
            <Button className="flex items-center space-x-2">
              <CalendarPlus className="h-4 w-4" />
              <span>Manage Appointments</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Today's Appointments</p>
                <p className="text-3xl font-bold text-blue-600">{stats.todayAppointments}</p>
              </div>
              <Calendar className="h-8 w-8 text-blue-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Pending Appointments</p>
                <p className="text-3xl font-bold text-yellow-600">{stats.pendingAppointments}</p>
              </div>
              <Clock className="h-8 w-8 text-yellow-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Completed Today</p>
                <p className="text-3xl font-bold text-green-600">{stats.completedAppointments}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Total Patients</p>
                <p className="text-3xl font-bold text-purple-600">{stats.totalPatients}</p>
              </div>
              <Users className="h-8 w-8 text-purple-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">New Patients Today</p>
                <p className="text-3xl font-bold text-teal-600">{stats.newPatientsToday}</p>
              </div>
              <TrendingUp className="h-8 w-8 text-teal-600" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Today's Appointments Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Activity className="h-5 w-5" />
              <span>Today's Appointments</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {todayAppointments.length === 0 ? (
              <div className="text-center py-8">
                <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                <p className="text-gray-500">No appointments scheduled for today</p>
                <Link to="/dashboard/reception/appointments">
                  <Button className="mt-3" size="sm">
                    Schedule Appointment
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {todayAppointments.map((appointment) => (
                  <div key={appointment.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <div className="flex-1">
                          <p className="font-medium text-gray-900">{appointment.patient_name}</p>
                          <p className="text-sm text-gray-600">{appointment.doctor_name}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-medium">{appointment.appointment_time}</p>
                          <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(appointment.status)}`}>
                            {appointment.status}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
                {todayAppointments.length >= 5 && (
                  <div className="text-center pt-3">
                    <Link to="/dashboard/reception/appointments">
                      <Button variant="outline" size="sm">
                        View All Appointments
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3">
              <Link to="/dashboard/reception/patients">
                <Button variant="outline" className="w-full justify-start">
                  <UserPlus className="h-4 w-4 mr-2" />
                  Register New Patient
                </Button>
              </Link>
              <Link to="/dashboard/reception/appointments">
                <Button variant="outline" className="w-full justify-start">
                  <CalendarPlus className="h-4 w-4 mr-2" />
                  Schedule Appointment
                </Button>
              </Link>
              <Link to="/dashboard/reception/appointments">
                <Button variant="outline" className="w-full justify-start">
                  <Calendar className="h-4 w-4 mr-2" />
                  View Today's Schedule
                </Button>
              </Link>
              <Button variant="outline" className="w-full justify-start" onClick={fetchDashboardData}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh Dashboard
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Lab Orders & Prescriptions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Today's Lab Orders */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <TestTube className="h-5 w-5" />
              <span>Today's Lab Orders</span>
              <Badge variant="outline" className="ml-2">{labOrders.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {labOrders.length === 0 ? (
              <div className="text-center py-6">
                <TestTube className="h-10 w-10 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No lab orders for today</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {labOrders.map((order) => (
                  <div key={order.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <p className="font-medium text-gray-900 truncate">{order.patient_name}</p>
                        <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>
                          {order.status}
                        </Badge>
                      </div>
                      <p className="text-sm text-gray-600 truncate">{order.test_name}</p>
                      <p className="text-xs text-gray-400">#{order.order_number} • {order.doctor_name}</p>
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                        onClick={() => showLabBillPreview(order)} title="View/Print Bill">
                        <Receipt className="h-3 w-3 mr-1" />Bill
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Prescriptions */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <FileText className="h-5 w-5" />
              <span>Recent Prescriptions</span>
              <Badge variant="outline" className="ml-2">{recentPrescriptions.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {recentPrescriptions.length === 0 ? (
              <div className="text-center py-6">
                <FileText className="h-10 w-10 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No recent prescriptions</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {recentPrescriptions.map((rx) => (
                  <div key={rx.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 truncate">{rx.patient_name}</p>
                      <p className="text-sm text-gray-600 truncate">{rx.doctor_name}</p>
                      <p className="text-xs text-gray-400">
                        #{rx.prescription_id} • {new Date(rx.prescription_date).toLocaleDateString()} • {rx.medicines?.length || 0} medicines
                      </p>
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs text-purple-600 border-purple-300"
                        onClick={() => showPrescriptionPreview(rx)} title="Print Prescription">
                        <Printer className="h-3 w-3 mr-1" />Print
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bill Preview Dialog */}
      <Dialog open={showBillDialog} onOpenChange={closeBillDialog}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" />
              Bill Preview - {billData?.bill_number}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4 h-full">
            {billData && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-600">Patient</p>
                  <p className="font-semibold">{billData.patient_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Doctor</p>
                  <p className="font-semibold">{billData.doctor_name}</p>
                </div>
                {billData.total_amount > 0 && (
                  <div>
                    <p className="text-sm text-gray-600">Total Amount</p>
                    <p className="font-semibold text-green-600">₹{billData.total_amount?.toFixed(2)}</p>
                  </div>
                )}
              </div>
            )}
            {billPdfUrl ? (
              <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
                <iframe src={billPdfUrl} className="w-full h-full border-0" title="Bill Preview" />
              </div>
            ) : (
              <div className="flex-1 min-h-[200px] flex items-center justify-center text-gray-500">
                <p>No bill PDF available. Generate bill from the consultation first.</p>
              </div>
            )}
            <div className="flex gap-2 pt-4">
              <Button variant="outline" onClick={closeBillDialog} className="flex-1">Close</Button>
              {billPdfUrl && (
                <Button onClick={printBill} className="flex-1 bg-blue-600 hover:bg-blue-700">
                  <Printer className="h-4 w-4 mr-2" />Print Bill
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Prescription Preview Dialog */}
      <Dialog open={showPrescriptionDialog} onOpenChange={closePrescriptionDialog}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Prescription - {prescriptionData?.prescription_id}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4 h-full">
            {prescriptionData && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-sm text-gray-600">Patient</p>
                  <p className="font-semibold">{prescriptionData.patient_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Doctor</p>
                  <p className="font-semibold">{prescriptionData.doctor_name}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Date</p>
                  <p className="font-semibold">{new Date(prescriptionData.prescription_date).toLocaleDateString()}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Medicines</p>
                  <p className="font-semibold">{prescriptionData.medicines?.length || 0} items</p>
                </div>
              </div>
            )}
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {prescriptionPdfUrl && (
                <iframe src={prescriptionPdfUrl} className="w-full h-full border-0" title="Prescription Preview" />
              )}
            </div>
            <div className="flex gap-2 pt-4">
              <Button variant="outline" onClick={closePrescriptionDialog} className="flex-1">Close</Button>
              <Button onClick={printPrescription} className="flex-1 bg-purple-600 hover:bg-purple-700">
                <Printer className="h-4 w-4 mr-2" />Print Prescription
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReceptionDashboard;