import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { QtyInput } from '../../../components/ui/qty-input';
import { Label } from '../../../components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import { Textarea } from '../../../components/ui/textarea';
import {
  CalendarClock, Loader2, Plus, Trash2,
} from 'lucide-react';

const todayStr = () => new Date().toISOString().slice(0, 10);

const emptyDates = () => ({
  service_date: todayStr(),
  payment_date: todayStr(),
  reason: '',
  payment_method: 'cash',
});

const TYPES = [
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'misc', label: 'Misc bill' },
];

const parseFee = (v) => {
  if (v == null || v === '') return '';
  const n = String(v).replace(/[^\d.]/g, '');
  return n === '' ? '' : n;
};

function DatesPanel({ dates, setDates }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 p-3 rounded-md border bg-slate-50">
      <div>
        <Label className="text-xs">Service Date (revenue / tax)</Label>
        <Input
          type="date"
          value={dates.service_date}
          onChange={(e) => setDates({ ...dates, service_date: e.target.value })}
        />
      </div>
      <div>
        <Label className="text-xs">Payment Date (daily collection)</Label>
        <Input
          type="date"
          value={dates.payment_date}
          onChange={(e) => setDates({ ...dates, payment_date: e.target.value })}
        />
      </div>
      <div>
        <Label className="text-xs">Payment method</Label>
        <select
          className="w-full h-9 rounded-md border px-2 text-sm"
          value={dates.payment_method}
          onChange={(e) => setDates({ ...dates, payment_method: e.target.value })}
        >
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="upi">UPI</option>
          <option value="online">Online</option>
          <option value="bank_transfer">Bank transfer</option>
        </select>
      </div>
      <div>
        <Label className="text-xs">Reason (optional)</Label>
        <Input
          value={dates.reason}
          placeholder="Omitted bill / manual entry"
          onChange={(e) => setDates({ ...dates, reason: e.target.value })}
        />
      </div>
    </div>
  );
}

function ChargeSection({ title, onAdd, children }) {
  return (
    <div className="space-y-2 border rounded-md p-3">
      <div className="flex items-center justify-between">
        <Label className="font-medium">{title}</Label>
        <Button type="button" size="sm" variant="outline" onClick={onAdd}>
          <Plus className="h-3 w-3 mr-1" /> Add
        </Button>
      </div>
      {children}
    </div>
  );
}

const CatchUpBills = () => {
  const { toast } = useToast();
  const [type, setType] = useState('pharmacy');
  const [dates, setDates] = useState(emptyDates());
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [nurses, setNurses] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [ancillaryServices, setAncillaryServices] = useState([]);
  const [packages, setPackages] = useState([]);

  const [patientId, setPatientId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [lines, setLines] = useState([{ item_name: '', quantity: 1, unit_price: '' }]);
  const [affectStock, setAffectStock] = useState(false);

  // IP
  const [admitDoctorId, setAdmitDoctorId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [admissionDate, setAdmissionDate] = useState(`${todayStr()}T10:00`);
  const [dischargeDate, setDischargeDate] = useState(`${todayStr()}T18:00`);
  const [isObservation, setIsObservation] = useState(false);
  const [doctorVisits, setDoctorVisits] = useState([]);
  const [nurseVisits, setNurseVisits] = useState([]);
  const [ancillaryRows, setAncillaryRows] = useState([]);
  const [pharmacyIpLines, setPharmacyIpLines] = useState([]);
  const [packageId, setPackageId] = useState('');
  const [packagePrice, setPackagePrice] = useState('');
  const [preview, setPreview] = useState(null);
  const [appendAdmissionId, setAppendAdmissionId] = useState('');

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmDraft, setConfirmDraft] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [pdfPreview, setPdfPreview] = useState(null);

  const doctorById = (id) => doctors.find((d) => String(d.id) === String(id));
  const nurseById = (id) => nurses.find((n) => String(n.id) === String(id));
  const ipFeeForDoctor = (id) => parseFee(doctorById(id)?.inpatient_fee_inr);

  const loadMeta = async () => {
    try {
      const [docRes, histRes] = await Promise.all([
        axios.get('/api/hospital/doctors').catch(() => ({ data: [] })),
        axios.get('/api/admin/catch-up/history', { params: { limit: 30 } }).catch(() => ({ data: [] })),
      ]);
      setDoctors(Array.isArray(docRes.data) ? docRes.data : (docRes.data?.doctors || []));
      setHistory(Array.isArray(histRes.data) ? histRes.data : []);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadMeta();
  }, []);

  useEffect(() => {
    if (type === 'inpatient' || type === 'append') {
      Promise.all([
        axios.get('/api/inpatient/rooms').catch(() => ({ data: [] })),
        axios.get('/api/inpatient/nurses').catch(() => ({ data: [] })),
        axios.get('/api/inpatient/ancillary-services', { params: { active_only: true } }).catch(() => ({ data: [] })),
        axios.get('/api/inpatient/packages', { params: { active_only: true } }).catch(() => ({ data: [] })),
      ]).then(([roomRes, nurseRes, ancRes, pkgRes]) => {
        setRooms(Array.isArray(roomRes.data) ? roomRes.data : (roomRes.data?.rooms || []));
        setNurses(Array.isArray(nurseRes.data) ? nurseRes.data : []);
        setAncillaryServices(Array.isArray(ancRes.data) ? ancRes.data : []);
        setPackages(Array.isArray(pkgRes.data) ? pkgRes.data : []);
      });
    }
  }, [type]);

  const datesPayload = () => ({
    service_date: dates.service_date,
    payment_date: dates.payment_date,
    reason: dates.reason?.trim() || null,
    payment_method: dates.payment_method,
  });

  const buildIpPayload = () => {
    const visits = [
      ...doctorVisits
        .filter((v) => v.visitor_id && v.visit_datetime)
        .map((v) => ({
          visit_type: 'doctor_visit',
          visitor_id: Number(v.visitor_id),
          visit_datetime: new Date(v.visit_datetime).toISOString(),
          charge_amount: Number(v.charge_amount || 0),
        })),
      ...nurseVisits
        .filter((v) => v.visitor_id && v.visit_datetime)
        .map((v) => ({
          visit_type: 'nurse_visit',
          visitor_id: Number(v.visitor_id),
          visit_datetime: new Date(v.visit_datetime).toISOString(),
          charge_amount: Number(v.charge_amount || 0),
        })),
    ];

    const ancillary = ancillaryRows
      .filter((a) => a.service_id)
      .map((a) => ({
        service_id: Number(a.service_id),
        quantity: Number(a.quantity || 1),
        unit_price: a.unit_price === '' ? null : Number(a.unit_price),
        charged_at: a.charged_at ? new Date(a.charged_at).toISOString() : null,
      }));

    const pharmacy_lines = pharmacyIpLines
      .filter((l) => l.item_name && l.unit_price !== '')
      .map((l) => ({
        item_name: l.item_name,
        quantity: Number(l.quantity || 1),
        unit_price: Number(l.unit_price || 0),
      }));

    return {
      ...datesPayload(),
      patient_id: patientId,
      admitting_doctor_id: Number(admitDoctorId),
      room_id: Number(roomId),
      admission_date: new Date(admissionDate).toISOString(),
      discharge_date: new Date(dischargeDate).toISOString(),
      admission_type: 'elective',
      is_observation: isObservation,
      visits,
      ancillary,
      pharmacy_lines,
      surgery_package_id: packageId ? Number(packageId) : null,
      surgery_package_price: packageId && packagePrice !== '' ? Number(packagePrice) : null,
      deposits: [],
    };
  };

  const lineItemsPayload = () => lines
    .filter((l) => l.item_name && l.unit_price !== '')
    .map((l) => ({
      item_name: l.item_name,
      quantity: Number(l.quantity || 1),
      unit_price: Number(l.unit_price || 0),
      ...(type === 'misc' ? { item_type: 'misc' } : {}),
    }));

  /** Build create/preview request for the active tab. Throws on validation. */
  const buildRequestBody = () => {
    if (type === 'pharmacy') {
      if (!patientId) throw new Error('Patient is required for pharmacy catch-up');
      const items = lineItemsPayload();
      if (!items.length) throw new Error('Add at least one line');
      return {
        url: '/api/admin/catch-up/pharmacy-sale',
        previewUrl: '/api/admin/catch-up/pharmacy-sale/preview',
        body: {
          ...datesPayload(),
          patient_id: patientId,
          items,
          affect_stock: affectStock,
        },
      };
    }
    if (type === 'misc') {
      if (!patientId) throw new Error('Patient is required');
      const items = lineItemsPayload();
      if (!items.length) throw new Error('Add at least one line');
      return {
        url: '/api/admin/catch-up/misc-bill',
        previewUrl: '/api/admin/catch-up/misc-bill/preview',
        body: {
          ...datesPayload(),
          patient_id: patientId,
          items,
        },
      };
    }
    if (type === 'inpatient') {
      if (!patientId || !admitDoctorId || !roomId) {
        throw new Error('Patient, admitting doctor, and room are required');
      }
      return {
        url: '/api/admin/catch-up/inpatient-stay',
        previewUrl: '/api/admin/catch-up/inpatient-stay/preview',
        body: buildIpPayload(),
      };
    }
    if (type === 'append') {
      if (!appendAdmissionId) throw new Error('Catch-up admission ID is required');
      const ip = buildIpPayload();
      const body = {
        ...datesPayload(),
        visits: ip.visits,
        ancillary: ip.ancillary,
        pharmacy_lines: ip.pharmacy_lines,
      };
      if (!body.visits.length && !body.ancillary.length
          && !body.pharmacy_lines.length) {
        throw new Error('Add at least one charge to append');
      }
      const items = [];
      body.visits.forEach((v) => {
        items.push({
          item_name: (v.visit_type || 'visit').replace(/_/g, ' '),
          quantity: 1,
          unit_price: Number(v.charge_amount || 0),
          total_price: Number(v.charge_amount || 0),
        });
      });
      body.ancillary.forEach((a) => {
        const svc = ancillaryServices.find((s) => String(s.id) === String(a.service_id));
        const unit = a.unit_price != null ? Number(a.unit_price) : Number(svc?.default_charge || 0);
        const qty = Number(a.quantity || 1);
        items.push({
          item_name: svc?.service_name || svc?.name || `Service #${a.service_id}`,
          quantity: qty,
          unit_price: unit,
          total_price: Math.round(unit * qty * 100) / 100,
        });
      });
      body.pharmacy_lines.forEach((li) => {
        const total = Math.round(Number(li.unit_price) * Number(li.quantity) * 100) / 100;
        items.push({
          item_name: li.item_name,
          quantity: li.quantity,
          unit_price: li.unit_price,
          total_price: total,
        });
      });
      const grand = items.reduce((s, i) => s + Number(i.total_price || 0), 0);
      return {
        url: `/api/admin/catch-up/inpatient/${Number(appendAdmissionId)}/append-charges`,
        previewUrl: null,
        localDraft: {
          bill_type: 'admission_append',
          patient_name: selectedPatient
            ? `${selectedPatient.first_name || ''} ${selectedPatient.last_name || ''}`.trim()
            : null,
          service_date: dates.service_date,
          payment_date: dates.payment_date,
          payment_method: dates.payment_method,
          items,
          subtotal: grand,
          grand_total: grand,
          creates_central_bill: true,
          warnings: [
            'Append will cancel the current paid final bill, add these charges, and re-finalize.',
            'Totals below are new charges only — not the full re-finalized bill.',
          ],
        },
        body,
      };
    }
    throw new Error('Unknown catch-up type');
  };

  const errMsg = (err) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message;
    return err.message || 'Request failed';
  };

  const fetchDraftPreview = async () => {
    const req = buildRequestBody();
    if (req.localDraft) return req.localDraft;
    const { data } = await axios.post(req.previewUrl, req.body);
    return data;
  };

  const openConfirm = async () => {
    setPreviewing(true);
    try {
      const draft = await fetchDraftPreview();
      setConfirmDraft(draft);
      setPreview(draft);
      setConfirmOpen(true);
    } catch (err) {
      toast({ title: 'Preview failed', description: errMsg(err), variant: 'destructive' });
    } finally {
      setPreviewing(false);
    }
  };

  const runPreview = async () => {
    setPreviewing(true);
    try {
      const draft = await fetchDraftPreview();
      setPreview(draft);
      setConfirmDraft(draft);
      setConfirmOpen(true);
    } catch (err) {
      toast({ title: 'Preview failed', description: errMsg(err), variant: 'destructive' });
    } finally {
      setPreviewing(false);
    }
  };

  const executeSubmit = async () => {
    setSaving(true);
    try {
      const req = buildRequestBody();
      const res = await axios.post(req.url, req.body);
      toast({
        title: 'Catch-up saved',
        description: res?.data?.bill_number
          ? `Bill ${res.data.bill_number} — ₹${res.data.total}`
          : `Total ₹${res?.data?.total ?? ''}`,
      });
      setConfirmOpen(false);
      setConfirmDraft(null);
      if (res?.data?.pdf?.path) {
        setPdfPreview({
          title: res.data.pdf.title || `Bill ${res.data.bill_number || ''}`.trim(),
          path: res.data.pdf.path,
        });
      }
      setDates(emptyDates());
      setLines([{ item_name: '', quantity: 1, unit_price: '' }]);
      setSelectedPatient(null);
      setPatientId(null);
      setDoctorVisits([]);
      setNurseVisits([]);
      setAncillaryRows([]);
      setPharmacyIpLines([]);
      setPackageId('');
      setPackagePrice('');
      setPreview(null);
      setAppendAdmissionId('');
      loadMeta();
    } catch (err) {
      toast({ title: 'Error', description: errMsg(err), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const updateLine = (idx, key, val) => {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [key]: val } : l)));
  };

  const nurseLabel = (n) => n.first_name
    ? `${n.first_name} ${n.last_name || ''}`.trim()
    : (n.name || `Nurse #${n.id}`);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-6 w-6 text-blue-600" />
        <div>
          <h2 className="text-2xl font-bold">Catch-up Bills</h2>
          <p className="text-sm text-muted-foreground">
            Enter omitted bills with a Service Date and Payment Date. Reason is optional.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {TYPES.map((t) => (
          <Button
            key={t.id}
            type="button"
            variant={type === t.id ? 'default' : 'outline'}
            size="sm"
            onClick={() => setType(t.id)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dates</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <DatesPanel dates={dates} setDates={setDates} />
          {type !== 'append' && (
            <PatientSearchPicker
              value={selectedPatient}
              onChange={(p) => {
                setSelectedPatient(p);
                setPatientId(p?.id ?? null);
              }}
              label="Patient"
              required
              compact
            />
          )}

          {['pharmacy', 'misc'].includes(type) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Line items</Label>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setLines((p) => [...p, { item_name: '', quantity: 1, unit_price: '' }])}
                >
                  <Plus className="h-3 w-3 mr-1" /> Add line
                </Button>
              </div>
              {lines.map((l, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-6">
                    <Label className="text-xs">Name</Label>
                    <Input value={l.item_name} onChange={(e) => updateLine(idx, 'item_name', e.target.value)} />
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs">Qty</Label>
                    <QtyInput min="1" step="1" value={l.quantity} onChange={(e) => updateLine(idx, 'quantity', e.target.value)} />
                  </div>
                  <div className="col-span-3">
                    <Label className="text-xs">Unit price</Label>
                    <Input type="number" min="0" step="0.01" value={l.unit_price} onChange={(e) => updateLine(idx, 'unit_price', e.target.value)} />
                  </div>
                  <div className="col-span-1">
                    <Button type="button" size="icon" variant="ghost" onClick={() => setLines((p) => p.filter((_, i) => i !== idx))}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {type === 'pharmacy' && (
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={affectStock} onChange={(e) => setAffectStock(e.target.checked)} />
                  Deduct pharmacy stock (off by default — financial catch-up only; requires medicine/batch ids via API)
                </label>
              )}
            </div>
          )}

          {(type === 'inpatient' || type === 'append') && (
            <div className="space-y-4">
              {type === 'append' && (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 space-y-2">
                  <p className="text-sm text-amber-900">
                    Append omitted charges to an existing catch-up stay. This cancels the paid final bill,
                    adds the new lines, and re-finalizes with the Service / Payment dates above.
                  </p>
                  <div>
                    <Label>Catch-up admission ID</Label>
                    <Input
                      type="number"
                      min="1"
                      placeholder="e.g. from history or inpatient list"
                      value={appendAdmissionId}
                      onChange={(e) => setAppendAdmissionId(e.target.value)}
                    />
                  </div>
                </div>
              )}

              {type === 'inpatient' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>Admitting doctor</Label>
                  <select
                    className="w-full h-9 rounded-md border px-2 text-sm"
                    value={admitDoctorId}
                    onChange={(e) => setAdmitDoctorId(e.target.value)}
                  >
                    <option value="">Select</option>
                    {doctors.map((d) => (
                      <option key={d.id} value={d.id}>{d.first_name} {d.last_name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>Room (rate snapshot only — no live bed claim)</Label>
                  <select
                    className="w-full h-9 rounded-md border px-2 text-sm"
                    value={roomId}
                    onChange={(e) => setRoomId(e.target.value)}
                  >
                    <option value="">Select room</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.room_number || r.name} — ₹{r.room_charge_per_day}/day
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>Admission datetime</Label>
                  <Input type="datetime-local" value={admissionDate} onChange={(e) => setAdmissionDate(e.target.value)} />
                </div>
                <div>
                  <Label>Discharge datetime</Label>
                  <Input type="datetime-local" value={dischargeDate} onChange={(e) => setDischargeDate(e.target.value)} />
                </div>
              </div>
              )}
              {type === 'inpatient' && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isObservation} onChange={(e) => setIsObservation(e.target.checked)} />
                Observation (skip room rent)
              </label>
              )}

              {type === 'inpatient' && (
              <div>
                <Label>Surgery package (optional)</Label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-1">
                  <select
                    className="w-full h-9 rounded-md border px-2 text-sm"
                    value={packageId}
                    onChange={(e) => {
                      const id = e.target.value;
                      setPackageId(id);
                      const pkg = packages.find((p) => String(p.id) === String(id));
                      setPackagePrice(pkg ? String(pkg.base_price ?? '') : '');
                    }}
                  >
                    <option value="">None</option>
                    {packages.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.package_name} — ₹{p.base_price}
                        {p.included_stay_days
                          ? ` · ${p.included_stay_days}d included`
                          : ''}
                      </option>
                    ))}
                  </select>
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="Agreed package price"
                    value={packagePrice}
                    disabled={!packageId}
                    onChange={(e) => setPackagePrice(e.target.value)}
                  />
                </div>
                {packageId && (() => {
                  const pkg = packages.find((p) => String(p.id) === String(packageId));
                  if (!pkg) return null;
                  const days = Number(pkg.included_stay_days || 0);
                  return (
                    <p className="text-xs text-muted-foreground mt-1">
                      {days > 0
                        ? `Package covers ${days} room-day(s); extra days bill as excess room stay.`
                        : (pkg.included_services || []).includes('room')
                          ? 'Package covers room for the full stay (no excess room).'
                          : 'No included stay days on this package — full room rent applies.'}
                    </p>
                  );
                })()}
              </div>
              )}

              <ChargeSection
                title="Doctor visits"
                onAdd={() => setDoctorVisits((p) => [...p, {
                  visitor_id: admitDoctorId || '',
                  visit_datetime: admissionDate,
                  charge_amount: ipFeeForDoctor(admitDoctorId),
                }])}
              >
                {doctorVisits.length === 0 && (
                  <p className="text-xs text-muted-foreground">No doctor visits added</p>
                )}
                {doctorVisits.map((v, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2">
                    <div className="col-span-4">
                      <select
                        className="w-full h-9 rounded-md border px-2 text-sm"
                        value={v.visitor_id}
                        onChange={(e) => {
                          const id = e.target.value;
                          setDoctorVisits((p) => p.map((x, i) => i === idx ? {
                            ...x,
                            visitor_id: id,
                            charge_amount: ipFeeForDoctor(id) || x.charge_amount,
                          } : x));
                        }}
                      >
                        <option value="">Doctor</option>
                        {doctors.map((d) => (
                          <option key={d.id} value={d.id}>{d.first_name} {d.last_name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-4">
                      <Input
                        type="datetime-local"
                        value={v.visit_datetime}
                        onChange={(e) => setDoctorVisits((p) => p.map((x, i) => i === idx ? { ...x, visit_datetime: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-3">
                      <Input
                        type="number"
                        placeholder="Charge"
                        value={v.charge_amount}
                        onChange={(e) => setDoctorVisits((p) => p.map((x, i) => i === idx ? { ...x, charge_amount: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-1">
                      <Button type="button" size="icon" variant="ghost" onClick={() => setDoctorVisits((p) => p.filter((_, i) => i !== idx))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </ChargeSection>

              <ChargeSection
                title="Nurse visits"
                onAdd={() => setNurseVisits((p) => [...p, {
                  visitor_id: nurses[0]?.id || '',
                  visit_datetime: admissionDate,
                  charge_amount: parseFee(nurses[0]?.inpatient_fee_inr) || '',
                }])}
              >
                {nurseVisits.length === 0 && (
                  <p className="text-xs text-muted-foreground">No nurse visits added</p>
                )}
                {nurseVisits.map((v, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2">
                    <div className="col-span-4">
                      <select
                        className="w-full h-9 rounded-md border px-2 text-sm"
                        value={v.visitor_id}
                        onChange={(e) => {
                          const id = e.target.value;
                          const n = nurseById(id);
                          setNurseVisits((p) => p.map((x, i) => i === idx ? {
                            ...x,
                            visitor_id: id,
                            charge_amount: parseFee(n?.inpatient_fee_inr) || x.charge_amount,
                          } : x));
                        }}
                      >
                        <option value="">Nurse</option>
                        {nurses.map((n) => (
                          <option key={n.id} value={n.id}>{nurseLabel(n)}</option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-4">
                      <Input
                        type="datetime-local"
                        value={v.visit_datetime}
                        onChange={(e) => setNurseVisits((p) => p.map((x, i) => i === idx ? { ...x, visit_datetime: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-3">
                      <Input
                        type="number"
                        placeholder="Charge"
                        value={v.charge_amount}
                        onChange={(e) => setNurseVisits((p) => p.map((x, i) => i === idx ? { ...x, charge_amount: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-1">
                      <Button type="button" size="icon" variant="ghost" onClick={() => setNurseVisits((p) => p.filter((_, i) => i !== idx))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </ChargeSection>

              <ChargeSection
                title="Ancillary charges"
                onAdd={() => setAncillaryRows((p) => [...p, {
                  service_id: ancillaryServices[0]?.id || '',
                  quantity: 1,
                  unit_price: ancillaryServices[0]?.default_charge ?? '',
                  charged_at: admissionDate,
                }])}
              >
                {ancillaryRows.length === 0 && (
                  <p className="text-xs text-muted-foreground">No ancillary charges added</p>
                )}
                {ancillaryRows.map((a, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2">
                    <div className="col-span-5">
                      <select
                        className="w-full h-9 rounded-md border px-2 text-sm"
                        value={a.service_id}
                        onChange={(e) => {
                          const id = e.target.value;
                          const svc = ancillaryServices.find((s) => String(s.id) === String(id));
                          setAncillaryRows((p) => p.map((x, i) => i === idx ? {
                            ...x,
                            service_id: id,
                            unit_price: svc?.default_charge ?? x.unit_price,
                          } : x));
                        }}
                      >
                        <option value="">Service</option>
                        {ancillaryServices.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.service_name} ({s.category}) — ₹{s.default_charge}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-2">
                      <QtyInput
                        min="0"
                        step="0.01"
                        placeholder="Qty"
                        value={a.quantity}
                        onChange={(e) => setAncillaryRows((p) => p.map((x, i) => i === idx ? { ...x, quantity: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-2">
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="Price"
                        value={a.unit_price}
                        onChange={(e) => setAncillaryRows((p) => p.map((x, i) => i === idx ? { ...x, unit_price: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-2">
                      <Input
                        type="datetime-local"
                        value={a.charged_at}
                        onChange={(e) => setAncillaryRows((p) => p.map((x, i) => i === idx ? { ...x, charged_at: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-1">
                      <Button type="button" size="icon" variant="ghost" onClick={() => setAncillaryRows((p) => p.filter((_, i) => i !== idx))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </ChargeSection>


              <ChargeSection
                title="Medicine bills (financial — no stock deduction)"
                onAdd={() => setPharmacyIpLines((p) => [...p, { item_name: '', quantity: 1, unit_price: '' }])}
              >
                {pharmacyIpLines.length === 0 && (
                  <p className="text-xs text-muted-foreground">No medicine lines added</p>
                )}
                {pharmacyIpLines.map((l, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2">
                    <div className="col-span-6">
                      <Input
                        placeholder="Medicine name"
                        value={l.item_name}
                        onChange={(e) => setPharmacyIpLines((p) => p.map((x, i) => i === idx ? { ...x, item_name: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-2">
                      <QtyInput
                        min="0"
                        step="0.01"
                        value={l.quantity}
                        onChange={(e) => setPharmacyIpLines((p) => p.map((x, i) => i === idx ? { ...x, quantity: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-3">
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="Unit price"
                        value={l.unit_price}
                        onChange={(e) => setPharmacyIpLines((p) => p.map((x, i) => i === idx ? { ...x, unit_price: e.target.value } : x))}
                      />
                    </div>
                    <div className="col-span-1">
                      <Button type="button" size="icon" variant="ghost" onClick={() => setPharmacyIpLines((p) => p.filter((_, i) => i !== idx))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </ChargeSection>

              {type === 'inpatient' && preview && preview.stay_days != null && (
                <p className="text-sm text-muted-foreground">
                  Last preview: {preview.stay_days}d stay
                  {preview.included_stay_days
                    ? ` (${preview.included_stay_days}d in package`
                      + (preview.excess_room_days
                        ? `, ${preview.excess_room_days}d excess room`
                        : ', no excess room')
                      + ')'
                    : ''}
                  {' · '}₹{preview.grand_total}
                </p>
              )}
            </div>
          )}

          <div className="pt-2 flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={runPreview} disabled={previewing || saving}>
              {previewing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Preview bill
            </Button>
            <Button onClick={openConfirm} disabled={saving || previewing}>
              {(saving || previewing) && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {type === 'append' ? 'Review & append' : 'Review & save'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent catch-up entries</CardTitle>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No catch-up actions yet.</p>
          ) : (
            <div className="space-y-2 text-sm">
              {history.map((h) => (
                <div key={h.id} className="border-b pb-2">
                  <div className="font-medium">{h.description || h.action}</div>
                  <div className="text-xs text-muted-foreground">
                    {h.timestamp} — {h.user_name}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={confirmOpen} onOpenChange={(v) => { if (!v && !saving) setConfirmOpen(false); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Confirm catch-up bill</DialogTitle>
          </DialogHeader>
          {confirmDraft && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2 text-muted-foreground">
                <div>Patient: <span className="text-foreground">{confirmDraft.patient_name || '—'}</span></div>
                <div>Type: <span className="text-foreground">{confirmDraft.bill_type}</span></div>
                <div>Service date: <span className="text-foreground">{confirmDraft.service_date}</span></div>
                <div>Payment date: <span className="text-foreground">{confirmDraft.payment_date}</span></div>
                <div>Method: <span className="text-foreground">{confirmDraft.payment_method}</span></div>
                <div>
                  Central bill:{' '}
                  <span className="text-foreground">
                    {confirmDraft.creates_central_bill === false ? 'No' : 'Yes'}
                  </span>
                </div>
              </div>
              {(confirmDraft.warnings || []).length > 0 && (
                <ul className="list-disc pl-5 text-amber-700 text-xs space-y-1">
                  {confirmDraft.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              <div className="border rounded-md overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left p-2 font-medium">Item</th>
                      <th className="text-right p-2 font-medium">Qty</th>
                      <th className="text-right p-2 font-medium">Rate</th>
                      <th className="text-right p-2 font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(confirmDraft.items || []).map((it, i) => (
                      <tr key={i} className="border-t">
                        <td className="p-2">{it.item_name}</td>
                        <td className="p-2 text-right">{it.quantity}</td>
                        <td className="p-2 text-right">₹{Number(it.unit_price || 0).toFixed(2)}</td>
                        <td className="p-2 text-right">
                          ₹{Number(it.total_price != null ? it.total_price : (it.quantity * it.unit_price) || 0).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                    {!(confirmDraft.items || []).length && (
                      <tr>
                        <td colSpan={4} className="p-3 text-center text-muted-foreground">No line items</td>
                      </tr>
                    )}
                  </tbody>
                  <tfoot>
                    <tr className="border-t bg-slate-50 font-semibold">
                      <td className="p-2" colSpan={3}>Total</td>
                      <td className="p-2 text-right">₹{Number(confirmDraft.grand_total || 0).toFixed(2)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => setConfirmOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="button" onClick={executeSubmit} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Confirm &amp; create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={!!pdfPreview}
        onClose={() => setPdfPreview(null)}
        title={pdfPreview?.title || 'Bill Preview'}
        path={pdfPreview?.path || null}
      />
    </div>
  );
};

export default CatchUpBills;
