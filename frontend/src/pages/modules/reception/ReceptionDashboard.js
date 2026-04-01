import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import LabTestBookingDialog from '../../../components/LabTestBookingDialog';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
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
  Eye,
  Download,
  ArrowRight,
  Package
} from 'lucide-react';

const ReceptionDashboard = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
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

  // Register patient dialog
  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [registerLoading, setRegisterLoading] = useState(false);
  const emptyPatientForm = {
    first_name: '', last_name: '', date_of_birth: '', gender: '',
    blood_group: '', marital_status: '', abha_id: '', email: '',
    primary_phone: '', emergency_contact_name: '', emergency_contact_phone: '',
    emergency_contact_relation: '', address_line1: '', address_line2: '',
    village: '', mandal: '', district: '',
  };
  const [patientForm, setPatientForm] = useState(emptyPatientForm);
  const [loading, setLoading] = useState(true);

  // Lab test booking dialog
  const [showLabBooking, setShowLabBooking] = useState(false);

  // Enabled modules
  const [enabledModules, setEnabledModules] = useState({});
  useEffect(() => {
    const fetchModules = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/system/enabled-modules', { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) {
          const mods = await res.json();
          const map = {};
          mods.forEach(m => { map[m.module_name] = m.is_enabled; });
          setEnabledModules(map);
        }
      } catch {
        setEnabledModules({ outpatient: true, lab: true });
      }
    };
    fetchModules();
  }, []);

  // Dialog states
  const [showPrescriptionDialog, setShowPrescriptionDialog] = useState(false);
  const [prescriptionPdfUrl, setPrescriptionPdfUrl] = useState(null);
  const [prescriptionData, setPrescriptionData] = useState(null);
  const [rxIncludeHeader, setRxIncludeHeader] = useState(true);

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

  const createPatient = async () => {
    setRegisterLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/patients/', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(patientForm)
      });
      if (response.ok) {
        setShowRegisterDialog(false);
        setPatientForm(emptyPatientForm);
        toast({ title: 'Success', description: 'Patient registered successfully!' });
        fetchDashboardData();
      } else {
        const err = await response.json();
        toast({ title: 'Registration Failed', description: err.detail || 'Unknown error', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Error registering patient', variant: 'destructive' });
    } finally {
      setRegisterLoading(false);
    }
  };

  // Lab payment dialog
  const [showLabPaymentDialog, setShowLabPaymentDialog] = useState(false);
  const [pendingLabOrders, setPendingLabOrders] = useState([]);
  const [labPaymentLoading, setLabPaymentLoading] = useState(false);
  const [labPaymentMethod, setLabPaymentMethod] = useState('cash');
  const [labDiscount, setLabDiscount] = useState(0);
  const [labBillHeader, setLabBillHeader] = useState(true);
  const [labBillPdfUrl, setLabBillPdfUrl] = useState(null);
  const [labBillOrderIds, setLabBillOrderIds] = useState([]);
  const [showLabBillPreview, setShowLabBillPreview] = useState(false);
  const [labPreviewHeader, setLabPreviewHeader] = useState(true);
  const [allLabOrdersForPatient, setAllLabOrdersForPatient] = useState([]);


  const openLabPaymentDialog = async (patientId) => {
    setLabPaymentLoading(true);
    setShowLabPaymentDialog(true);
    setPendingLabOrders([]);
    setAllLabOrdersForPatient([]);
    try {
      const token = localStorage.getItem('token');
      const [pendingRes, allRes] = await Promise.all([
        fetch(`/api/lab/orders/patient/${patientId}/pending-payment`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`/api/lab/orders/patient/${patientId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);
      if (pendingRes.ok) setPendingLabOrders(await pendingRes.json());
      if (allRes.ok) setAllLabOrdersForPatient(await allRes.json());
    } catch (err) {
      console.error('Failed to fetch lab orders:', err);
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const collectAllLabPayments = async () => {
    if (pendingLabOrders.length === 0) return;
    const patientId = pendingLabOrders[0].patient_id;
    setLabPaymentLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/patient/${patientId}/bill`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method: labPaymentMethod, discount_amount: labDiscount, include_header: labBillHeader })
      });
      if (res.ok) {
        const orderIdsHeader = res.headers.get('X-Order-Ids');
        const ids = orderIdsHeader ? orderIdsHeader.split(',').map(Number) : [];
        setLabBillOrderIds(ids);
        setLabPreviewHeader(labBillHeader);

        const blob = await res.blob();
        if (labBillPdfUrl) window.URL.revokeObjectURL(labBillPdfUrl);
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
        setLabBillPdfUrl(url);
        setShowLabBillPreview(true);
        setPendingLabOrders([]);
        setLabDiscount(0);
        toast({ title: 'Success', description: 'Lab bill generated and payment collected' });
        fetchDashboardData();
      } else {
        const err = await res.json();
        toast({ variant: 'destructive', title: 'Error', description: err.detail || 'Bill generation failed' });
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate lab bill' });
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const downloadLabReport = async (reportId, orderNumber, includeHeader = true, packageBookingId = null) => {
    try {
      const token = localStorage.getItem('token');
      const url = packageBookingId
        ? `/api/lab/reports/package/${packageBookingId}/download?include_header=${includeHeader}`
        : `/api/lab/reports/${reportId}/download?include_header=${includeHeader}`;
      const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = packageBookingId ? `${orderNumber}_report.pdf` : `lab_report_${orderNumber}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
      } else {
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to download report' });
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to download report' });
    }
  };

  // Prescription preview
  const fetchRxPdf = async (prescriptionId, includeHeader) => {
    try {
      const token = localStorage.getItem('token');
      const pdfResponse = await fetch(`/api/prescriptions-simple/${prescriptionId}/download?include_header=${includeHeader}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (pdfResponse.ok) {
        const blob = await pdfResponse.blob();
        if (prescriptionPdfUrl) window.URL.revokeObjectURL(prescriptionPdfUrl);
        setPrescriptionPdfUrl(window.URL.createObjectURL(blob));
        setShowPrescriptionDialog(true);
      } else {
        toast({ title: 'Error', description: 'Failed to load prescription PDF', variant: 'destructive' });
      }
    } catch (error) {
      console.error('Error fetching prescription:', error);
      toast({ title: 'Error', description: 'Error loading prescription', variant: 'destructive' });
    }
  };

  const showPrescriptionPreview = async (prescription) => {
    setPrescriptionData(prescription);
    await fetchRxPdf(prescription.prescription_id, rxIncludeHeader);
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
          {enabledModules.outpatient && (
            <Link to="/dashboard/reception/appointments">
              <Button className="flex items-center space-x-2">
                <CalendarPlus className="h-4 w-4" />
                <span>Manage Appointments</span>
              </Button>
            </Link>
          )}
          {enabledModules.lab && (
            <Button variant="outline" className="flex items-center space-x-2" onClick={() => setShowLabBooking(true)}>
              <TestTube className="h-4 w-4" />
              <span>Book Lab Test</span>
            </Button>
          )}
        </div>
      </div>

      {/* Stats Cards */}
      <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-${enabledModules.outpatient ? '5' : '2'} gap-6`}>
        {enabledModules.outpatient && (
          <>
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
          </>
        )}

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

      {/* Today's Appointments Overview — only when outpatient enabled */}
      {enabledModules.outpatient && (
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
                  <div key={appointment.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
                    onClick={() => navigate('/dashboard/reception/appointments')}
                  >
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <div className="flex-1">
                          <p className="font-medium text-gray-900">{appointment.patient_name}</p>
                          <p className="text-sm text-gray-600">{appointment.doctor_name}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-medium">{appointment.appointment_time}</p>
                          <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(appointment.status)}`}>
                            {appointment.status.replace('_', ' ')}
                          </span>
                        </div>
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-gray-400 ml-2 flex-shrink-0" />
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
              <Button variant="outline" className="w-full justify-start" onClick={() => { setPatientForm(emptyPatientForm); setShowRegisterDialog(true); }}>
                <UserPlus className="h-4 w-4 mr-2" />
                Register New Patient
              </Button>
              {enabledModules.outpatient && (
                <>
                  <Button variant="outline" className="w-full justify-start" onClick={() => navigate('/dashboard/reception/appointments?action=schedule')}>
                    <CalendarPlus className="h-4 w-4 mr-2" />
                    Schedule Appointment
                  </Button>
                  <Link to="/dashboard/reception/appointments">
                    <Button variant="outline" className="w-full justify-start">
                      <Calendar className="h-4 w-4 mr-2" />
                      View Today's Schedule
                    </Button>
                  </Link>
                </>
              )}
              {enabledModules.lab && (
                <Button variant="outline" className="w-full justify-start" onClick={() => setShowLabBooking(true)}>
                  <TestTube className="h-4 w-4 mr-2" />
                  Book Lab Test
                </Button>
              )}
              <Button variant="outline" className="w-full justify-start" onClick={fetchDashboardData}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh Dashboard
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      )}

      {/* Lab Orders & Prescriptions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Today's Lab Orders — only when lab enabled */}
        {enabledModules.lab && (<>
        {/* Today's Lab Orders */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center space-x-2">
                <TestTube className="h-5 w-5" />
                <span>Today's Lab Orders</span>
                <Badge variant="outline" className="ml-2">{labOrders.length}</Badge>
              </CardTitle>
              <div className="flex gap-2">
                <Link to="/dashboard/reception/packages">
                  <Button size="sm" variant="outline" className="text-xs">
                    <Package className="h-3.5 w-3.5 mr-1" /> Book Package
                  </Button>
                </Link>
                <Link to="/dashboard/reception/appointments">
                  <Button variant="ghost" size="sm" className="text-xs text-gray-500">
                    View All <ArrowRight className="h-3 w-3 ml-1" />
                  </Button>
                </Link>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {labOrders.length === 0 ? (
              <div className="text-center py-6">
                <TestTube className="h-10 w-10 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No lab orders for today</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {(() => {
                  const groups = [];
                  const pkgMap = {};
                  for (const order of labOrders) {
                    if (order.package_booking_id) {
                      if (!pkgMap[order.package_booking_id]) {
                        pkgMap[order.package_booking_id] = { name: order.package_name || 'Package', orders: [] };
                        groups.push({ type: 'package', key: order.package_booking_id, data: pkgMap[order.package_booking_id] });
                      }
                      pkgMap[order.package_booking_id].orders.push(order);
                    } else {
                      groups.push({ type: 'single', key: order.id, data: order });
                    }
                  }
                  return groups.map(g => {
                    if (g.type === 'package') {
                      const pkg = g.data;
                      const first = pkg.orders[0];
                      return (
                        <div key={g.key} className="border-2 border-indigo-200 bg-indigo-50/30 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-indigo-200">
                            <Package className="h-4 w-4 text-indigo-600" />
                            <span className="font-semibold text-indigo-700 text-sm">{pkg.name}</span>
                            <Badge className="bg-indigo-100 text-indigo-700 text-xs">{pkg.orders.length} tests</Badge>
                            <span className="text-xs text-gray-500 ml-auto">{first.patient_name} • {first.doctor_name}</span>
                          </div>
                          <div className="space-y-1.5">
                            {pkg.orders.map(order => (
                              <div key={order.id} className="flex items-center justify-between bg-white rounded p-2 border border-indigo-100">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium truncate">{order.test_name}</span>
                                    <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>{order.status}</Badge>
                                    <Badge className={`text-xs ${order.payment_status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                      {order.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                                    </Badge>
                                  </div>
                                  <p className="text-xs text-gray-400">#{order.order_number}</p>
                                </div>
                                <div className="flex items-center gap-1 ml-2">
                                  {order.has_report && (
                                    <>
                                      <Button size="sm" variant="outline" className="h-6 px-2 text-xs"
                                        onClick={() => downloadLabReport(order.report_id, order.order_number, true)}>
                                        <Download className="h-3 w-3 mr-1" />With Header
                                      </Button>
                                      <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                                        onClick={() => downloadLabReport(order.report_id, order.order_number, false)}>
                                        Without Header
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                          <div className="mt-2 pt-2 border-t border-indigo-200 flex gap-2 flex-wrap">
                            {pkg.orders.some(o => o.payment_status !== 'paid') && (
                              <Button size="sm" className="h-7 px-3 text-xs"
                                onClick={() => openLabPaymentDialog(first.patient_id)}>
                                Collect Payment
                              </Button>
                            )}
                            {pkg.orders.some(o => o.has_report) && (
                              <>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-indigo-300 text-indigo-700"
                                  onClick={() => downloadLabReport(null, pkg.name, true, g.key)}>
                                  <Download className="h-3 w-3 mr-1" />All Reports (With Header)
                                </Button>
                                <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-indigo-600"
                                  onClick={() => downloadLabReport(null, pkg.name, false, g.key)}>
                                  Without Header
                                </Button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    }
                    const order = g.data;
                    return (
                      <div key={order.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-2">
                            <p className="font-medium text-gray-900 truncate">{order.patient_name}</p>
                            <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>{order.status}</Badge>
                            <Badge className={`text-xs ${order.payment_status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                              {order.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600 truncate">{order.test_name} — ₹{(order.amount || 0).toFixed(0)}</p>
                          <p className="text-xs text-gray-400">#{order.order_number} • {order.doctor_name}</p>
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                          {order.payment_status !== 'paid' && (
                            <Button size="sm" className="h-7 px-2 text-xs"
                              onClick={() => openLabPaymentDialog(order.patient_id)}>
                              Collect Payment
                            </Button>
                          )}
                          {order.has_report && (
                            <>
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                onClick={() => downloadLabReport(order.report_id, order.order_number, true)}>
                                <Download className="h-3 w-3 mr-1" />With Header
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                                onClick={() => downloadLabReport(order.report_id, order.order_number, false)}>
                                Without Header
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
            )}
          </CardContent>
        </Card>

        </>)}

        {/* Recent Prescriptions — only when outpatient enabled */}
        {enabledModules.outpatient && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5" />
                <span>Recent Prescriptions</span>
                <Badge variant="outline" className="ml-2">{recentPrescriptions.length}</Badge>
              </CardTitle>
              <Link to="/dashboard/reception/appointments">
                <Button variant="ghost" size="sm" className="text-xs text-gray-500">
                  View All <ArrowRight className="h-3 w-3 ml-1" />
                </Button>
              </Link>
            </div>
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
        )}
      </div>

      {/* Lab Payment Dialog */}
      <Dialog open={showLabPaymentDialog} onOpenChange={setShowLabPaymentDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube className="h-5 w-5" />
              Lab Order Payments
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {labPaymentLoading ? (
              <div className="text-center py-8 text-gray-500">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                Loading...
              </div>
            ) : pendingLabOrders.length === 0 && allLabOrdersForPatient.filter(o => o.has_report).length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <TestTube className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                <p>No pending lab payments for this patient.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {pendingLabOrders.length > 0 && (
                  <>
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-700">Pending Payment ({pendingLabOrders.length})</p>
                      <p className="font-semibold text-green-700">
                        Total: ₹{pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0).toFixed(2)}
                      </p>
                    </div>
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {pendingLabOrders.map(order => (
                        <div key={order.id} className="p-3 flex items-center justify-between">
                          <div>
                            <p className="font-medium text-sm">{order.test_name}</p>
                            <p className="text-xs text-gray-500">{order.order_number} | {order.test_code} | {order.doctor_name}</p>
                          </div>
                          <p className="font-semibold text-sm">₹{(order.amount || 0).toFixed(2)}</p>
                        </div>
                      ))}
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span>Subtotal</span>
                        <span>₹{pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0).toFixed(2)}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span>Discount</span>
                        <div className="flex items-center gap-1">
                          <span className="text-gray-400">₹</span>
                          <Input
                            type="number"
                            min="0"
                            step="0.01"
                            value={labDiscount || ''}
                            onChange={(e) => setLabDiscount(parseFloat(e.target.value) || 0)}
                            placeholder="0"
                            className="w-24 h-7 text-right text-sm"
                          />
                        </div>
                      </div>
                      <hr />
                      <div className="flex items-center justify-between font-semibold">
                        <span>Total</span>
                        <span>₹{(pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0) - labDiscount).toFixed(2)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <Label className="text-xs">Payment Method</Label>
                        <Select value={labPaymentMethod} onValueChange={setLabPaymentMethod}>
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="cash">Cash</SelectItem>
                            <SelectItem value="card">Card</SelectItem>
                            <SelectItem value="upi">UPI</SelectItem>
                            <SelectItem value="online">Online</SelectItem>
                            <SelectItem value="insurance">Insurance</SelectItem>
                            <SelectItem value="cheque">Cheque</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-center space-x-2 mt-4">
                        <input type="checkbox" id="lab-bill-header" checked={labBillHeader}
                          onChange={(e) => setLabBillHeader(e.target.checked)} className="w-4 h-4" />
                        <Label htmlFor="lab-bill-header" className="text-xs">Include header</Label>
                      </div>
                    </div>
                    <Button className="w-full" onClick={collectAllLabPayments} disabled={labPaymentLoading}>
                      {labPaymentLoading ? 'Generating Bill...' : `Pay & Download Bill (₹${(pendingLabOrders.reduce((sum, o) => sum + (o.amount || 0), 0) - labDiscount).toFixed(2)})`}
                    </Button>
                  </>
                )}

                {allLabOrdersForPatient.filter(o => o.has_report).length > 0 && (
                  <>
                    {pendingLabOrders.length > 0 && <hr className="my-2" />}
                    <p className="text-sm font-medium text-gray-700">Completed Reports</p>
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {allLabOrdersForPatient.filter(o => o.has_report).map(order => (
                        <div key={order.id} className="p-3 flex items-center justify-between">
                          <div>
                            <p className="font-medium text-sm">{order.test_name}</p>
                            <p className="text-xs text-gray-500">{order.order_number} | {order.test_code}</p>
                          </div>
                          <div className="flex gap-1">
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => downloadLabReport(order.report_id, order.order_number, true)}>
                              <Download className="h-3 w-3 mr-1" />With Header
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => downloadLabReport(order.report_id, order.order_number, false)}>
                              Without Header
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
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
            <div className="flex items-center justify-between pt-4">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rxIncludeHeader}
                  onChange={async (e) => {
                    const val = e.target.checked;
                    setRxIncludeHeader(val);
                    if (prescriptionData) {
                      await fetchRxPdf(prescriptionData.prescription_id, val);
                    }
                  }}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-600">Include hospital letterhead</span>
              </label>
              <div className="flex gap-2">
                <Button variant="outline" onClick={closePrescriptionDialog}>Close</Button>
                <Button onClick={printPrescription} className="bg-purple-600 hover:bg-purple-700">
                  <Printer className="h-4 w-4 mr-2" />Print
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Register Patient Dialog */}
      <Dialog open={showRegisterDialog} onOpenChange={setShowRegisterDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register New Patient</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>First Name *</Label>
              <Input value={patientForm.first_name} onChange={(e) => setPatientForm({...patientForm, first_name: e.target.value})} />
            </div>
            <div>
              <Label>Last Name *</Label>
              <Input value={patientForm.last_name} onChange={(e) => setPatientForm({...patientForm, last_name: e.target.value})} />
            </div>
            <div>
              <Label>Date of Birth</Label>
              <Input type="date" value={patientForm.date_of_birth} onChange={(e) => setPatientForm({...patientForm, date_of_birth: e.target.value})} />
            </div>
            <div>
              <Label>Gender</Label>
              <Select value={patientForm.gender} onValueChange={(v) => setPatientForm({...patientForm, gender: v})}>
                <SelectTrigger><SelectValue placeholder="Select Gender" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Male">Male</SelectItem>
                  <SelectItem value="Female">Female</SelectItem>
                  <SelectItem value="Other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Blood Group</Label>
              <Select value={patientForm.blood_group} onValueChange={(v) => setPatientForm({...patientForm, blood_group: v})}>
                <SelectTrigger><SelectValue placeholder="Select Blood Group" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="A+">A+</SelectItem>
                  <SelectItem value="A-">A-</SelectItem>
                  <SelectItem value="B+">B+</SelectItem>
                  <SelectItem value="B-">B-</SelectItem>
                  <SelectItem value="AB+">AB+</SelectItem>
                  <SelectItem value="AB-">AB-</SelectItem>
                  <SelectItem value="O+">O+</SelectItem>
                  <SelectItem value="O-">O-</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Marital Status</Label>
              <Select value={patientForm.marital_status} onValueChange={(v) => setPatientForm({...patientForm, marital_status: v})}>
                <SelectTrigger><SelectValue placeholder="Select Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Single">Single</SelectItem>
                  <SelectItem value="Married">Married</SelectItem>
                  <SelectItem value="Widowed">Widowed</SelectItem>
                  <SelectItem value="Divorced">Divorced</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>ABHA ID</Label>
              <Input value={patientForm.abha_id} onChange={(e) => setPatientForm({...patientForm, abha_id: e.target.value})} placeholder="14-digit ABHA number" />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={patientForm.email} onChange={(e) => setPatientForm({...patientForm, email: e.target.value})} />
            </div>
            <div>
              <Label>Primary Phone *</Label>
              <Input value={patientForm.primary_phone} onChange={(e) => setPatientForm({...patientForm, primary_phone: e.target.value})} />
            </div>

            <div className="col-span-2 border-t pt-3 mt-2">
              <Label className="text-sm font-semibold text-gray-700">Emergency Contact</Label>
            </div>
            <div>
              <Label>Contact Name</Label>
              <Input value={patientForm.emergency_contact_name} onChange={(e) => setPatientForm({...patientForm, emergency_contact_name: e.target.value})} />
            </div>
            <div>
              <Label>Contact Phone</Label>
              <Input value={patientForm.emergency_contact_phone} onChange={(e) => setPatientForm({...patientForm, emergency_contact_phone: e.target.value})} />
            </div>
            <div>
              <Label>Relation</Label>
              <Select value={patientForm.emergency_contact_relation} onValueChange={(v) => setPatientForm({...patientForm, emergency_contact_relation: v})}>
                <SelectTrigger><SelectValue placeholder="Select Relation" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Spouse">Spouse</SelectItem>
                  <SelectItem value="Parent">Parent</SelectItem>
                  <SelectItem value="Child">Child</SelectItem>
                  <SelectItem value="Sibling">Sibling</SelectItem>
                  <SelectItem value="Friend">Friend</SelectItem>
                  <SelectItem value="Other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="col-span-2 border-t pt-3 mt-2">
              <Label className="text-sm font-semibold text-gray-700">Address</Label>
            </div>
            <div className="col-span-2">
              <Label>Address Line 1</Label>
              <Input value={patientForm.address_line1} onChange={(e) => setPatientForm({...patientForm, address_line1: e.target.value})} placeholder="House/Flat No, Street" />
            </div>
            <div className="col-span-2">
              <Label>Address Line 2</Label>
              <Input value={patientForm.address_line2} onChange={(e) => setPatientForm({...patientForm, address_line2: e.target.value})} placeholder="Area, Landmark" />
            </div>
            <div>
              <Label>Village / Town</Label>
              <Input value={patientForm.village} onChange={(e) => setPatientForm({...patientForm, village: e.target.value})} />
            </div>
            <div>
              <Label>Mandal / Taluka</Label>
              <Input value={patientForm.mandal} onChange={(e) => setPatientForm({...patientForm, mandal: e.target.value})} />
            </div>
            <div>
              <Label>District</Label>
              <Input value={patientForm.district} onChange={(e) => setPatientForm({...patientForm, district: e.target.value})} />
            </div>
          </div>
          <div className="flex gap-2 pt-4">
            <Button variant="outline" onClick={() => setShowRegisterDialog(false)} className="flex-1">Cancel</Button>
            <Button onClick={createPatient} disabled={registerLoading || !patientForm.first_name || !patientForm.last_name || !patientForm.primary_phone} className="flex-1">
              {registerLoading ? 'Registering...' : 'Register Patient'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Lab Test Booking Dialog */}
      <LabTestBookingDialog
        open={showLabBooking}
        onClose={(success) => { setShowLabBooking(false); if (success) fetchDashboardData(); }}
      />

      {/* Lab Bill Preview Dialog */}
      <Dialog open={showLabBillPreview} onOpenChange={() => {
        if (labBillPdfUrl) { window.URL.revokeObjectURL(labBillPdfUrl); setLabBillPdfUrl(null); }
        setShowLabBillPreview(false);
      }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" /> Lab Bill Preview
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4">
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {labBillPdfUrl && (
                <iframe src={labBillPdfUrl} className="w-full h-full min-h-[400px] border-0" title="Lab Bill Preview" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center space-x-2">
                <input type="checkbox" id="lab-preview-header" checked={labPreviewHeader}
                  onChange={async (e) => {
                    const newVal = e.target.checked;
                    setLabPreviewHeader(newVal);
                    if (labBillOrderIds.length > 0) {
                      try {
                        const token = localStorage.getItem('token');
                        const res = await fetch('/api/lab/orders/regenerate-bill', {
                          method: 'POST',
                          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                          body: JSON.stringify({ order_ids: labBillOrderIds, include_header: newVal }),
                        });
                        if (res.ok) {
                          if (labBillPdfUrl) window.URL.revokeObjectURL(labBillPdfUrl);
                          const blob = await res.blob();
                          setLabBillPdfUrl(window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })));
                        }
                      } catch {}
                    }
                  }}
                  className="w-4 h-4" />
                <Label htmlFor="lab-preview-header" className="text-sm">Include header</Label>
              </div>
              <Button variant="outline" onClick={() => {
                if (labBillPdfUrl) { window.URL.revokeObjectURL(labBillPdfUrl); setLabBillPdfUrl(null); }
                setShowLabBillPreview(false);
              }} className="flex-1">Close</Button>
              <Button onClick={() => {
                if (labBillPdfUrl) {
                  const iframe = document.createElement('iframe');
                  iframe.style.display = 'none';
                  document.body.appendChild(iframe);
                  iframe.src = labBillPdfUrl;
                  iframe.onload = () => {
                    iframe.contentWindow.print();
                    setTimeout(() => document.body.removeChild(iframe), 1000);
                  };
                }
              }} className="flex-1 bg-blue-600 hover:bg-blue-700">
                <Printer className="h-4 w-4 mr-2" /> Print Bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReceptionDashboard;