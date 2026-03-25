import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Search, X, TestTube, Loader2, Plus } from 'lucide-react';

const LabTestBookingDialog = ({ open, onClose, patient = null, referralList = [] }) => {
  const token = localStorage.getItem('token');
  const [loading, setLoading] = useState(false);

  // Patient search (if not pre-selected)
  const [patientSearch, setPatientSearch] = useState('');
  const [patientResults, setPatientResults] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(patient);

  // Tests
  const [tests, setTests] = useState([]);
  const [testSearch, setTestSearch] = useState('');
  const [selectedTests, setSelectedTests] = useState([]);

  // Payment
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [discount, setDiscount] = useState(0);
  const [referredBy, setReferredBy] = useState('');
  const [includeHeader, setIncludeHeader] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [duplicateWarning, setDuplicateWarning] = useState(null);

  useEffect(() => {
    if (open) {
      setSelectedPatient(patient);
      setSelectedTests([]);
      setDuplicateWarning(null);
      setDiscount(0);
      setPaymentMethod('cash');
      setReferredBy('');
      fetchTests();
    }
  }, [open, patient]);

  const fetchTests = async () => {
    try {
      const res = await fetch('/api/lab/tests', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setTests(await res.json());
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

    // Check for duplicate orders today (skip if user already confirmed)
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
            return; // Stop — show warning, user must click "Proceed Anyway"
          }
        } else {
          console.warn('Duplicate check failed:', checkRes.status, await checkRes.text());
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
          referred_by: referredBy || null,
          discount_amount: discount,
          include_header: includeHeader,
        }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
        const printWin = window.open(url, '_blank');
        if (printWin) {
          printWin.addEventListener('load', () => {
            setTimeout(() => printWin.print(), 500);
          });
        }
        onClose(true); // true = success
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to book lab tests');
      }
    } catch {
      alert('Failed to book lab tests');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredTests = tests.filter(t => {
    if (!testSearch) return true;
    const q = testSearch.toLowerCase();
    return t.name.toLowerCase().includes(q) || (t.test_code || '').toLowerCase().includes(q);
  });

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TestTube className="h-5 w-5" /> Book Lab Tests
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Patient Selection */}
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

          {/* Test Selection */}
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

            {/* Selected tests tags */}
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

          {/* Payment + Referral */}
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
          </div>

          {/* Bill Summary */}
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

          {/* Duplicate Warning */}
          {duplicateWarning && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
              <p className="text-sm font-semibold text-amber-800 flex items-center gap-1.5">
                <span className="text-amber-500 text-lg">&#9888;</span>
                These tests were already booked and paid for this patient today:
              </p>
              <ul className="space-y-1 ml-6">
                {duplicateWarning.map((d, i) => (
                  <li key={i} className="text-sm text-amber-700">
                    <span className="font-medium">{d.test_name}</span>
                    <span className="text-amber-500 text-xs ml-1">(booked at {d.order_time})</span>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => setDuplicateWarning(null)}>
                  Go Back & Edit
                </Button>
                <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => handleSubmit(true)}>
                  Proceed Anyway
                </Button>
              </div>
            </div>
          )}

          {/* Header toggle + Submit */}
          <div className={`flex items-center justify-between pt-2 border-t ${duplicateWarning ? 'hidden' : ''}`}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={includeHeader} onChange={e => setIncludeHeader(e.target.checked)} className="rounded" />
              Include header in bill
            </label>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
              <Button onClick={handleSubmit}
                disabled={submitting || !selectedPatient || selectedTests.length === 0}>
                {submitting ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Booking...</> : `Book & Print Bill (₹${total.toFixed(2)})`}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default LabTestBookingDialog;
