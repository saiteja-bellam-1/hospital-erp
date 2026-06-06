import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Search, X, TestTube, Loader2, Plus, Printer } from 'lucide-react';
import { printPdfFromUrl } from '../utils/printPdf';

const LabTestBookingDialog = ({ open, onClose, patient = null, referralList = [] }) => {
  const token = localStorage.getItem('token');
  const [loading, setLoading] = useState(false);

  const [patientSearch, setPatientSearch] = useState('');
  const [patientResults, setPatientResults] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(patient);

  const [tests, setTests] = useState([]);
  const [testSearch, setTestSearch] = useState('');
  const [selectedTests, setSelectedTests] = useState([]);

  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [discount, setDiscount] = useState(0);
  const [doctors, setDoctors] = useState([]);
  const [doctorId, setDoctorId] = useState('');
  const [referredBy, setReferredBy] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [duplicateWarning, setDuplicateWarning] = useState(null);

  const [billPdfUrl, setBillPdfUrl] = useState(null);
  const [showBillPreview, setShowBillPreview] = useState(false);

  useEffect(() => {
    if (open) {
      setSelectedPatient(patient);
      setSelectedTests([]);
      setDuplicateWarning(null);
      setDiscount(0);
      setPaymentMethod('cash');
      setDoctorId('');
      setReferredBy('');
      setBillPdfUrl(null);
      setShowBillPreview(false);
      fetchDoctors();
      fetchTests();
    }
  }, [open, patient]);

  const fetchTests = async () => {
    try {
      const res = await fetch('/api/lab/tests', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setTests(await res.json());
    } catch {}
  };

  const fetchDoctors = async () => {
    try {
      const res = await fetch('/api/appointments/doctors', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setDoctors(await res.json());
    } catch {}
  };

  const searchPatients = async (q) => {
    setPatientSearch(q);
    if (q.length < 2) { setPatientResults([]); return; }
    try {
      const res = await fetch(`/api/patients/?search=${q}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setPatientResults(await res.json());
    } catch {}
  };

  const toggleTest = (test) => {
    if (selectedTests.find(t => t.id === test.id)) {
      setSelectedTests(selectedTests.filter(t => t.id !== test.id));
    } else {
      setSelectedTests([...selectedTests, test]);
    }
  };

  const subtotal = selectedTests.reduce((sum, t) => sum + (t.cost || 0), 0);
  const total = Math.max(subtotal - discount, 0);

  const handleSubmit = async (force = false) => {
    if (!selectedPatient || selectedTests.length === 0) return;

    if (!force) {
      try {
        const checkRes = await fetch('/api/lab/orders/check-duplicates', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ patient_id: selectedPatient.id, test_ids: selectedTests.map(t => t.id) }),
        });
        if (checkRes.ok) {
          const { duplicates } = await checkRes.json();
          if (duplicates.length > 0) {
            setDuplicateWarning(duplicates);
            return;
          }
        }
      } catch (err) {
        console.warn('Duplicate check error:', err);
      }
    }

    setDuplicateWarning(null);
    setSubmitting(true);
    try {
      const res = await fetch('/api/lab/orders/reception-book', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: selectedPatient.id,
          test_ids: selectedTests.map(t => t.id),
          payment_method: paymentMethod,
          doctor_id: doctorId ? parseInt(doctorId, 10) : null,
          referred_by: referredBy || null,
          discount_amount: discount,
          force: force,
        }),
      });
      if (res.ok) {
        const blob = await res.blob();
        if (billPdfUrl) window.URL.revokeObjectURL(billPdfUrl);
        setBillPdfUrl(window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })));
        setShowBillPreview(true);
      } else if (res.status === 409) {
        const err = await res.json();
        setDuplicateWarning(err.detail?.duplicates || []);
      } else {
        const err = await res.json();
        alert(typeof err.detail === 'string' ? err.detail : 'Failed to book lab tests');
      }
    } catch {
      alert('Failed to book lab tests');
    } finally {
      setSubmitting(false);
    }
  };

  const handlePrintBill = () => {
    printPdfFromUrl(billPdfUrl);
  };

  const closeBillPreview = () => {
    if (billPdfUrl) {
      window.URL.revokeObjectURL(billPdfUrl);
      setBillPdfUrl(null);
    }
    setShowBillPreview(false);
    onClose(true);
  };

  const filteredTests = tests.filter(t => {
    if (!testSearch) return true;
    const q = testSearch.toLowerCase();
    return t.name.toLowerCase().includes(q) || (t.test_code || '').toLowerCase().includes(q);
  });

  if (showBillPreview) {
    return (
      <Dialog open={true} onOpenChange={closeBillPreview}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube className="h-5 w-5" /> Lab Bill Preview
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4">
            <p className="text-xs text-muted-foreground">
              Letterhead follows Settings → Print Settings.
            </p>
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm text-gray-600">Patient</p>
                <p className="font-semibold">{selectedPatient?.first_name} {selectedPatient?.last_name}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Amount</p>
                <p className="font-semibold text-green-600">₹{total.toFixed(2)}</p>
              </div>
            </div>
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {billPdfUrl && (
                <iframe src={billPdfUrl} className="w-full h-full min-h-[400px] border-0" title="Bill Preview" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button variant="outline" onClick={closeBillPreview} className="flex-1">Close</Button>
              <Button onClick={handlePrintBill} className="flex-1 bg-blue-600 hover:bg-blue-700">
                <Printer className="h-4 w-4 mr-2" /> Print Bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TestTube className="h-5 w-5" /> Book Lab Tests
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {!selectedPatient ? (
            <div>
              <Label>Search Patient *</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input value={patientSearch} onChange={(e) => searchPatients(e.target.value)}
                  placeholder="Search by name or phone..." className="pl-10" />
              </div>
              {patientResults.length > 0 && (
                <div className="border rounded-lg mt-1 max-h-40 overflow-y-auto divide-y">
                  {patientResults.map(p => (
                    <div key={p.id} className="p-2 hover:bg-gray-50 cursor-pointer flex justify-between items-center"
                      onClick={() => { setSelectedPatient(p); setPatientResults([]); setPatientSearch(''); }}>
                      <div>
                        <p className="text-sm font-medium">{p.first_name} {p.last_name}</p>
                        <p className="text-xs text-gray-400">{p.primary_phone} | {p.gender}</p>
                      </div>
                      <Plus className="h-4 w-4 text-blue-500" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-between bg-blue-50 rounded-lg p-3">
              <div>
                <p className="text-sm font-semibold">{selectedPatient.first_name} {selectedPatient.last_name}</p>
                <p className="text-xs text-gray-500">{selectedPatient.primary_phone} | {selectedPatient.gender} | ID: {selectedPatient.patient_id}</p>
              </div>
              {!patient && (
                <Button size="sm" variant="ghost" onClick={() => setSelectedPatient(null)}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          )}

          <div>
            <Label>Select Tests *</Label>
            <div className="relative mt-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input value={testSearch} onChange={(e) => setTestSearch(e.target.value)}
                placeholder="Search tests..." className="pl-10" />
            </div>
            <div className="border rounded-lg mt-2 max-h-48 overflow-y-auto divide-y">
              {filteredTests.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">No tests found</p>
              ) : filteredTests.map(test => {
                const isSelected = selectedTests.some(t => t.id === test.id);
                return (
                  <div key={test.id}
                    className={`flex items-center justify-between p-2.5 cursor-pointer transition-colors ${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                    onClick={() => toggleTest(test)}>
                    <div className="flex items-center gap-2">
                      <input type="checkbox" checked={isSelected} readOnly className="w-4 h-4 rounded" />
                      <div>
                        <p className="text-sm font-medium">{test.name}</p>
                        <p className="text-xs text-gray-400">{test.test_code} | {test.sample_type || 'N/A'}</p>
                      </div>
                    </div>
                    <span className="text-sm font-semibold">₹{test.cost || 0}</span>
                  </div>
                );
              })}
            </div>
            {selectedTests.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {selectedTests.map(t => (
                  <Badge key={t.id} variant="secondary" className="flex items-center gap-1 cursor-pointer"
                    onClick={() => toggleTest(t)}>
                    {t.name} — ₹{t.cost || 0}
                    <X className="h-3 w-3" />
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
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
              <Label>Doctor</Label>
              <Select value={doctorId || '_none'} onValueChange={v => setDoctorId(v === '_none' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Select doctor..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">None</SelectItem>
                  {doctors.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      Dr. {d.first_name} {d.last_name}
                      {d.specialization ? ` — ${d.specialization}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Referred By</Label>
            {referralList.length > 0 ? (
              <Select value={referredBy || '_none'} onValueChange={v => setReferredBy(v === '_none' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Self / None</SelectItem>
                  {referralList.map(r => (
                    <SelectItem key={r.id} value={r.name}>{r.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={referredBy} onChange={e => setReferredBy(e.target.value)} placeholder="Referral name" />
            )}
          </div>

          {selectedTests.length > 0 && (
            <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
              <div className="flex justify-between text-sm">
                <span>Subtotal ({selectedTests.length} test{selectedTests.length > 1 ? 's' : ''})</span>
                <span>₹{subtotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm items-center">
                <span>Discount</span>
                <Input type="number" min={0} max={subtotal} value={discount}
                  onChange={e => setDiscount(Math.min(parseFloat(e.target.value) || 0, subtotal))}
                  className="w-24 h-7 text-right text-sm" />
              </div>
              <div className="flex justify-between font-bold text-base border-t pt-1.5">
                <span>Total</span>
                <span>₹{total.toFixed(2)}</span>
              </div>
            </div>
          )}

          {duplicateWarning && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
              <p className="text-sm font-semibold text-amber-800">Duplicate tests booked today:</p>
              <ul className="space-y-1 ml-6">
                {duplicateWarning.map((d, i) => (
                  <li key={i} className="text-sm text-amber-700">
                    <span className="font-medium">{d.test_name}</span>
                    <span className="text-amber-500 text-xs ml-1">(booked at {d.order_time})</span>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => setDuplicateWarning(null)}>Go Back</Button>
                <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => handleSubmit(true)}>Proceed Anyway</Button>
              </div>
            </div>
          )}

          <div className={`flex items-center justify-end pt-2 border-t gap-2 ${duplicateWarning ? 'hidden' : ''}`}>
            <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
            <Button onClick={() => handleSubmit(false)}
              disabled={submitting || !selectedPatient || selectedTests.length === 0}>
              {submitting ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Booking...</> : `Book & Print Bill (₹${total.toFixed(2)})`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default LabTestBookingDialog;
