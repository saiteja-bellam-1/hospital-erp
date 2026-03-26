import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import {
  Package, Search, TestTube, RefreshCw, ShoppingCart, Loader2
} from 'lucide-react';
import axios from 'axios';

const ReceptionPackagesPage = () => {
  const { toast } = useToast();
  const [packages, setPackages] = useState([]);
  const [packageCategories, setPackageCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Booking dialog
  const [showBookingDialog, setShowBookingDialog] = useState(false);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [patientSearch, setPatientSearch] = useState('');
  const [patientResults, setPatientResults] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [priority, setPriority] = useState('normal');
  const [notes, setNotes] = useState('');
  const [referredBy, setReferredBy] = useState('');
  const [bookingLoading, setBookingLoading] = useState(false);
  const [pkgIncludeHeader, setPkgIncludeHeader] = useState(true);
  const [referralList, setReferralList] = useState([]);
  const [pkgDuplicateWarning, setPkgDuplicateWarning] = useState(null);

  useEffect(() => {
    const fetchRefs = async () => {
      try {
        const res = await axios.get('/api/referrals', {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });
        setReferralList(res.data);
      } catch {}
    };
    fetchRefs();
  }, []);

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    try {
      const params = { active_only: true };
      if (categoryFilter !== 'all') params.category_id = categoryFilter;
      if (searchQuery) params.search = searchQuery;
      const res = await axios.get('/api/lab/packages', { params });
      setPackages(res.data);
    } catch (err) {
      console.error('Failed to fetch packages:', err);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, searchQuery]);

  const fetchCategories = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/packages/categories');
      setPackageCategories(res.data.filter(c => c.is_active));
    } catch (err) {
      console.error('Failed to fetch package categories:', err);
    }
  }, []);

  useEffect(() => { fetchCategories(); }, [fetchCategories]);
  useEffect(() => { fetchPackages(); }, [fetchPackages]);

  // Patient search
  const searchPatients = async (term) => {
    setPatientSearch(term);
    if (term.length < 2) { setPatientResults([]); return; }
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/patients/search', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ search_term: term, sort_by: 'name', sort_order: 'asc' })
      });
      if (res.ok) {
        const data = await res.json();
        setPatientResults(data.patients || []);
      }
    } catch (err) {
      console.error('Patient search failed:', err);
    }
  };

  const openBooking = (pkg) => {
    setSelectedPackage(pkg);
    setSelectedPatient(null);
    setPatientSearch('');
    setPatientResults([]);
    setPaymentMethod('cash');
    setPriority('normal');
    setNotes('');
    setReferredBy('');
    setShowBookingDialog(true);
  };

  const bookPackage = async (force = false) => {
    if (!selectedPatient || !selectedPackage) return;

    // Check for duplicate orders today
    if (!force) {
      try {
        const testIds = (selectedPackage.tests || []).map(t => t.id);
        const checkRes = await fetch('/api/lab/orders/check-duplicates', {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ patient_id: selectedPatient.id, test_ids: testIds }),
        });
        if (checkRes.ok) {
          const { duplicates } = await checkRes.json();
          if (duplicates.length > 0) {
            setPkgDuplicateWarning(duplicates);
            return;
          }
        }
      } catch {}
    }

    setPkgDuplicateWarning(null);
    setBookingLoading(true);
    try {
      const res = await axios.post(`/api/lab/packages/${selectedPackage.id}/book`, {
        patient_id: selectedPatient.id,
        priority,
        notes: notes || null,
        referred_by: referredBy || null,
        payment_method: paymentMethod,
        include_header: pkgIncludeHeader,
        force: force,
      }, { responseType: 'blob' });

      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `lab_package_bill_${selectedPackage.package_code}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);

      toast({ title: 'Success', description: `Package "${selectedPackage.name}" booked successfully!` });
      setShowBookingDialog(false);
    } catch (err) {
      console.error('Package booking failed:', err);
      if (err.response?.status === 409) {
        // 409 comes as blob due to responseType — parse it
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          setPkgDuplicateWarning(parsed.detail?.duplicates || []);
        } catch {
          toast({ title: 'Error', description: 'Duplicate orders detected. Please try again.', variant: 'destructive' });
        }
      } else {
        const detail = err.response?.data instanceof Blob
          ? 'Failed to book package'
          : (err.response?.data?.detail || 'Failed to book package');
        toast({ title: 'Error', description: typeof detail === 'string' ? detail : 'Failed to book package', variant: 'destructive' });
      }
    } finally {
      setBookingLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Package className="h-6 w-6" /> Lab Test Packages
        </h1>
        <Button variant="outline" size="sm" onClick={fetchPackages}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input placeholder="Search packages..." value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)} className="pl-10" />
        </div>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All Categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            {packageCategories.map(cat => (
              <SelectItem key={cat.id} value={String(cat.id)}>{cat.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Package List */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      ) : packages.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-gray-500">
            <Package className="h-12 w-12 mx-auto mb-3 text-gray-300" />
            <p className="text-lg font-medium">No packages available</p>
            <p className="text-sm mt-1">Ask your lab admin to create test packages.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {packages.map(pkg => (
            <Card key={pkg.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg">{pkg.name}</CardTitle>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline" className="text-xs">{pkg.package_code}</Badge>
                      <Badge variant="secondary" className="text-xs">{pkg.category_name}</Badge>
                    </div>
                  </div>
                  {pkg.discount_percentage > 0 && (
                    <Badge className="bg-green-100 text-green-700 text-sm font-semibold">
                      {pkg.discount_percentage}% OFF
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {pkg.description && (
                  <p className="text-sm text-gray-500 mb-3">{pkg.description}</p>
                )}

                {/* Tests included */}
                <div className="mb-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-1.5">
                    Tests Included ({pkg.tests.length})
                  </p>
                  <div className="space-y-1">
                    {pkg.tests.map(t => (
                      <div key={t.id} className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-1.5">
                          <TestTube className="h-3 w-3 text-gray-400" />
                          {t.name}
                        </span>
                        <span className="text-gray-400 text-xs">Rs. {t.cost}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Pricing */}
                <div className="bg-gray-50 rounded-lg p-3 mb-3">
                  <div className="flex justify-between text-sm text-gray-500">
                    <span>Individual Total</span>
                    <span className="line-through">Rs. {pkg.actual_price}</span>
                  </div>
                  <div className="flex justify-between font-bold text-lg mt-1">
                    <span>Package Price</span>
                    <span className="text-blue-600">Rs. {pkg.package_price}</span>
                  </div>
                  {pkg.discount_percentage > 0 && (
                    <p className="text-xs text-green-600 mt-1">
                      You save Rs. {(pkg.actual_price - pkg.package_price).toFixed(0)}
                    </p>
                  )}
                </div>

                <Button className="w-full" onClick={() => openBooking(pkg)}>
                  <ShoppingCart className="h-4 w-4 mr-2" /> Book Package
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Booking Dialog */}
      <Dialog open={showBookingDialog} onOpenChange={setShowBookingDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Book Package: {selectedPackage?.name}</DialogTitle>
          </DialogHeader>

          {selectedPackage && (
            <div className="space-y-4">
              {/* Package summary */}
              <div className="bg-blue-50 rounded-lg p-3">
                <div className="flex justify-between items-center">
                  <div>
                    <p className="font-semibold">{selectedPackage.name}</p>
                    <p className="text-xs text-gray-500">{selectedPackage.tests.length} tests included</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-gray-400 line-through">Rs. {selectedPackage.actual_price}</p>
                    <p className="text-lg font-bold text-blue-600">Rs. {selectedPackage.package_price}</p>
                  </div>
                </div>
              </div>

              {/* Patient Selection */}
              <div>
                <Label className="font-semibold">Patient *</Label>
                {selectedPatient ? (
                  <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg mt-1">
                    <div>
                      <p className="font-medium">{selectedPatient.first_name} {selectedPatient.last_name}</p>
                      <p className="text-xs text-gray-500">{selectedPatient.primary_phone} | {selectedPatient.patient_id}</p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => { setSelectedPatient(null); setPatientSearch(''); setPatientResults([]); }}>
                      Change
                    </Button>
                  </div>
                ) : (
                  <div className="mt-1">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                      <Input placeholder="Search patient by name or phone..."
                        value={patientSearch} onChange={(e) => searchPatients(e.target.value)}
                        className="pl-10" />
                    </div>
                    {patientResults.length > 0 && (
                      <div className="border rounded-lg mt-1 max-h-36 overflow-y-auto">
                        {patientResults.slice(0, 8).map(p => (
                          <div key={p.id} className="px-3 py-2 hover:bg-gray-50 cursor-pointer flex justify-between"
                            onClick={() => { setSelectedPatient(p); setPatientResults([]); }}>
                            <span className="text-sm font-medium">{p.first_name} {p.last_name}</span>
                            <span className="text-xs text-gray-400">{p.primary_phone}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Options */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Payment Method *</Label>
                  <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
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
                <div>
                  <Label>Priority</Label>
                  <Select value={priority} onValueChange={setPriority}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                      <SelectItem value="stat">STAT</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Referred By</Label>
                  <Select value={referredBy || '_none'} onValueChange={(v) => setReferredBy(v === '_none' ? '' : v)}>
                    <SelectTrigger><SelectValue placeholder="Select referral" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">Self / None</SelectItem>
                      {referralList.map(r => (
                        <SelectItem key={r.id} value={r.name}>
                          {r.name}{r.village ? ` — ${r.village}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Notes</Label>
                  <Input value={notes} onChange={(e) => setNotes(e.target.value)}
                    placeholder="Optional notes" />
                </div>
              </div>

              {/* Total */}
              <div className="bg-gray-50 p-3 rounded-lg">
                <div className="flex justify-between text-sm">
                  <span>Actual Price</span>
                  <span className="line-through text-gray-400">Rs. {selectedPackage.actual_price}</span>
                </div>
                <div className="flex justify-between text-sm text-green-600">
                  <span>Discount</span>
                  <span>- Rs. {(selectedPackage.actual_price - selectedPackage.package_price).toFixed(2)}</span>
                </div>
                <div className="flex justify-between font-bold text-lg border-t mt-2 pt-2">
                  <span>Amount to Pay</span>
                  <span>Rs. {selectedPackage.package_price}</span>
                </div>
              </div>

              {/* Duplicate Warning */}
              {pkgDuplicateWarning && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                  <p className="text-sm font-semibold text-amber-800 flex items-center gap-1.5">
                    <span className="text-amber-500 text-lg">&#9888;</span>
                    These tests were already booked and paid today:
                  </p>
                  <ul className="space-y-1 ml-6">
                    {pkgDuplicateWarning.map((d, i) => (
                      <li key={i} className="text-sm text-amber-700">
                        <span className="font-medium">{d.test_name}</span>
                        <span className="text-amber-500 text-xs ml-1">(at {d.order_time})</span>
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2 pt-1">
                    <Button size="sm" variant="outline" onClick={() => setPkgDuplicateWarning(null)}>Go Back</Button>
                    <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => bookPackage(true)}>
                      Proceed Anyway
                    </Button>
                  </div>
                </div>
              )}

              {!pkgDuplicateWarning && (
                <div className="flex items-center gap-3">
                  <div className="flex items-center space-x-2">
                    <input type="checkbox" id="pkg-include-header" checked={pkgIncludeHeader}
                      onChange={(e) => setPkgIncludeHeader(e.target.checked)} className="w-4 h-4" />
                    <Label htmlFor="pkg-include-header" className="text-sm">Include header</Label>
                  </div>
                  <Button variant="outline" onClick={() => setShowBookingDialog(false)} className="flex-1">Cancel</Button>
                  <Button onClick={() => bookPackage()} className="flex-1"
                    disabled={bookingLoading || !selectedPatient}>
                    {bookingLoading ? 'Booking...' : 'Book & Pay'}
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReceptionPackagesPage;
