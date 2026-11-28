import React, { useState, useEffect } from 'react';
import WhatsAppPdfButton from './WhatsAppPdfButton';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Search, X, TestTube, Loader2, Plus, Printer } from 'lucide-react';
import { printPdfFromUrl } from '../utils/printPdf';
import PatientSearchPicker from './PatientSearchPicker';
import ReferralSelectWithCreate from './ReferralSelectWithCreate';
import { useAuth } from '../contexts/AuthContext';
import { canSeeLabTestRates, normalizeUserRoles } from '../hooks/useNavigationSections';
import { defaultRateCardId, testPrice } from '../utils/labPricing';
import { patientReferralName } from '../utils/patientReferral';
import PaymentCollectionFields, {
  defaultPaymentValue, validatePayment, paymentRequestFields, amountCollectedNow, DEFAULT_PAYMENT_METHODS,
} from './billing/PaymentCollectionFields';

const LAB_BOOKING_METHODS = [...DEFAULT_PAYMENT_METHODS, { value: 'insurance', label: 'Insurance' }];

const LabTestBookingDialog = ({ open, onClose, patient = null, referralList, onReferralsChange }) => {
  const { user } = useAuth();
  const showRates = canSeeLabTestRates(normalizeUserRoles(user));
  const token = localStorage.getItem('token');
  const [loading, setLoading] = useState(false);

  const [selectedPatient, setSelectedPatient] = useState(patient);

  const [tests, setTests] = useState([]);
  const [testSearch, setTestSearch] = useState('');
  const [selectedTests, setSelectedTests] = useState([]);

  const [rateCards, setRateCards] = useState([]);
  const [rateCardId, setRateCardId] = useState('');
  const [payment, setPayment] = useState(defaultPaymentValue('cash'));
  const [discount, setDiscount] = useState('');
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
      setPayment(defaultPaymentValue('cash'));
      setDoctorId('');
      setReferredBy(patientReferralName(patient));
      setBillPdfUrl(null);
      setShowBillPreview(false);
      fetchDoctors();
      fetchTests();
      fetchRateCards();
    }
  }, [open, patient]);

  const fetchTests = async () => {
    try {
      const res = await fetch('/api/lab/tests', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setTests(await res.json());
    } catch {}
  };

  const fetchRateCards = async () => {
    try {
      const cardsRes = await fetch('/api/lab/rate-cards', { headers: { Authorization: `Bearer ${token}` } });
      if (cardsRes.ok) {
        const cards = await cardsRes.json();
        setRateCards(cards);
        setRateCardId(defaultRateCardId(cards));
      }
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

  const toggleTest = (test) => {
    if (selectedTests.find(t => t.id === test.id)) {
      setSelectedTests(selectedTests.filter(t => t.id !== test.id));
    } else {
      setSelectedTests([...selectedTests, test]);
    }
  };

  const subtotal = selectedTests.reduce((sum, t) => sum + testPrice(t, rateCardId), 0);
  const total = Math.max(subtotal - (parseFloat(discount) || 0), 0);

  const handleSubmit = async (force = false) => {
    if (!selectedPatient || selectedTests.length === 0) return;
    if (submitting) return;

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
          ...paymentRequestFields(payment),
          doctor_id: doctorId ? parseInt(doctorId, 10) : null,
          referred_by: referredBy || null,
          discount_amount: parseFloat(discount) || 0,
          force: force,
          rate_card_id: rateCardId ? parseInt(rateCardId, 10) : null,
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
              Letterhead follows Administration → Customisations.
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
              <WhatsAppPdfButton
                size="default"
                className="flex-1 h-10"
                kind="lab_order_confirmation"
                label="Confirm"
                phone={selectedPatient?.primary_phone}
                patientName={`${selectedPatient?.first_name || ''} ${selectedPatient?.last_name || ''}`.trim()}
                patientId={selectedPatient?.patient_id}
              />
              <WhatsAppPdfButton
                size="default"
                className="flex-1 h-10"
                kind="lab_invoice"
                label="Invoice"
                phone={selectedPatient?.primary_phone}
                patientName={`${selectedPatient?.first_name || ''} ${selectedPatient?.last_name || ''}`.trim()}
                patientId={selectedPatient?.patient_id}
                blobUrl={billPdfUrl}
                filename="lab-invoice.pdf"
              />
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
      <DialogContent className="max-w-5xl w-[96vw] flex flex-col gap-3 p-5 md:h-[min(90vh,760px)] md:overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <TestTube className="h-5 w-5" /> Book Lab Tests
          </DialogTitle>
        </DialogHeader>

        <div className="grid flex-1 min-h-0 gap-4 md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          {/* ── Left: patient + test picker ─────────────────────────── */}
          <div className="flex min-h-0 flex-col gap-3">
            {patient ? (
              <div className="shrink-0 rounded-lg bg-blue-50 px-3 py-2">
                <p className="text-sm font-semibold">{selectedPatient?.first_name} {selectedPatient?.last_name}</p>
                <p className="text-xs text-gray-500">{selectedPatient?.primary_phone} | {selectedPatient?.gender} | ID: {selectedPatient?.patient_id}</p>
              </div>
            ) : (
              <div className="shrink-0">
                <PatientSearchPicker
                  value={selectedPatient}
                  onChange={(next) => {
                    setSelectedPatient(next);
                    setReferredBy(patientReferralName(next));
                  }}
                  label="Search Patient"
                  required
                />
              </div>
            )}

            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-center justify-between">
                <Label>Select Tests *</Label>
                {selectedTests.length > 0 && (
                  <span className="text-xs text-gray-500">{selectedTests.length} selected</span>
                )}
              </div>
              <div className="relative mt-1 shrink-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input value={testSearch} onChange={(e) => setTestSearch(e.target.value)}
                  placeholder="Search by name or code..." className="pl-10 h-9" autoFocus={!!patient} />
              </div>
              <div className="mt-2 max-h-64 min-h-[120px] overflow-y-auto rounded-lg border divide-y md:max-h-none md:flex-1">
                {filteredTests.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-4">No tests found</p>
                ) : filteredTests.map(test => {
                  const isSelected = selectedTests.some(t => t.id === test.id);
                  return (
                    <div key={test.id}
                      className={`flex items-center justify-between px-2.5 py-2 cursor-pointer transition-colors ${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                      onClick={() => toggleTest(test)}>
                      <div className="flex min-w-0 items-center gap-2">
                        <input type="checkbox" checked={isSelected} readOnly className="w-4 h-4 rounded shrink-0" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{test.name}</p>
                          <p className="truncate text-xs text-gray-400">
                            {test.test_code} | {test.sample_type || 'N/A'}
                            {test.default_fulfillment === 'send_out' && (
                              <span className="text-amber-700">
                                {' · '}Sent to {test.default_partner_name || 'partner lab'}
                                {showRates && test.default_partner_cost != null ? ` (₹${Number(test.default_partner_cost).toFixed(2)})` : ''}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      {showRates && (
                        <span className="ml-2 shrink-0 text-sm font-semibold">₹{testPrice(test, rateCardId)}</span>
                      )}
                    </div>
                  );
                })}
              </div>
              {selectedTests.length > 0 && (
                <div className="mt-2 flex max-h-16 shrink-0 flex-wrap gap-1.5 overflow-y-auto">
                  {selectedTests.map(t => (
                    <Badge key={t.id} variant="secondary" className="flex items-center gap-1 cursor-pointer"
                      onClick={() => toggleTest(t)}>
                      {t.name}{showRates ? ` — ₹${testPrice(t, rateCardId)}` : ''}
                      <X className="h-3 w-3" />
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Right: details, bill, payment, actions ───────────────── */}
          <div className="flex min-h-0 flex-col gap-3 md:border-l md:pl-4">
            <div className="space-y-3 md:min-h-0 md:flex-1 md:overflow-y-auto md:pr-1">
              <div className={`grid gap-2 ${showRates ? 'grid-cols-2' : 'grid-cols-1'}`}>
                {showRates && (
                  <div>
                    <Label className="text-xs">Rate</Label>
                    <Select value={rateCardId || '_none'} onValueChange={(v) => setRateCardId(v === '_none' ? '' : v)}>
                      <SelectTrigger className="h-9"><SelectValue placeholder="Rate" /></SelectTrigger>
                      <SelectContent>
                        {rateCards.map((c) => (
                          <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div>
                  <Label className="text-xs">Doctor</Label>
                  <Select value={doctorId || '_none'} onValueChange={v => setDoctorId(v === '_none' ? '' : v)}>
                    <SelectTrigger className="h-9"><SelectValue placeholder="Select doctor..." /></SelectTrigger>
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
              <ReferralSelectWithCreate
                value={referredBy}
                onValueChange={setReferredBy}
                locked={!!patientReferralName(selectedPatient)}
                referrals={referralList}
                onReferralsChange={onReferralsChange}
              />

              <div className="rounded-lg border bg-gray-50 p-3 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span>Subtotal ({selectedTests.length} test{selectedTests.length === 1 ? '' : 's'})</span>
                  <span>₹{subtotal.toFixed(2)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Discount</span>
                  <div className="flex items-center gap-1">
                    <span className="text-gray-400">₹</span>
                    <Input type="number" min={0} max={subtotal} value={discount ?? ''}
                      onChange={e => setDiscount(e.target.value)} placeholder="0"
                      disabled={selectedTests.length === 0}
                      className="w-24 h-7 text-right text-sm bg-white" />
                  </div>
                </div>
                <div className="flex justify-between border-t pt-1.5 text-base font-bold">
                  <span>Total</span>
                  <span>₹{total.toFixed(2)}</span>
                </div>
              </div>

              {total > 0 ? (
                <PaymentCollectionFields
                  total={total}
                  value={payment}
                  methods={LAB_BOOKING_METHODS}
                  onChange={setPayment}
                />
              ) : (
                <p className="text-xs text-gray-500">Select tests to see the bill and payment options.</p>
              )}

              {duplicateWarning && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                  <p className="text-sm font-semibold text-amber-800">Duplicate tests booked today:</p>
                  <ul className="space-y-1 ml-5 list-disc">
                    {duplicateWarning.map((d, i) => (
                      <li key={i} className="text-sm text-amber-700">
                        <span className="font-medium">{d.test_name}</span>
                        <span className="text-amber-500 text-xs ml-1">(booked at {d.order_time})</span>
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2 pt-1">
                    <Button size="sm" variant="outline" onClick={() => setDuplicateWarning(null)}>Go Back</Button>
                    <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => handleSubmit(true)} disabled={submitting}>
                      {submitting ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Booking...</> : 'Proceed Anyway'}
                    </Button>
                  </div>
                </div>
              )}
            </div>

            <div className={`shrink-0 flex items-center justify-end gap-2 border-t pt-3 ${duplicateWarning ? 'hidden' : ''}`}>
              <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
              <Button className="flex-1" onClick={() => handleSubmit(false)}
                disabled={submitting || !selectedPatient || selectedTests.length === 0 || !!validatePayment(payment, total)}>
                {submitting ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Booking...</>
                  : payment.mode === 'later' ? 'Book & Print Bill (pay later)'
                  : `Book & Print Bill · collect ₹${amountCollectedNow(payment, total).toFixed(2)}`}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default LabTestBookingDialog;
