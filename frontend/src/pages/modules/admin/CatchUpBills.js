import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { useToast } from '../../../hooks/use-toast';
import { CalendarClock, Loader2, Plus, Trash2 } from 'lucide-react';

const todayStr = () => new Date().toISOString().slice(0, 10);

const emptyDates = () => ({
  service_date: todayStr(),
  payment_date: todayStr(),
  reason: '',
  payment_method: 'cash',
});

const TYPES = [
  { id: 'consultation', label: 'Consultation' },
  { id: 'lab', label: 'Lab' },
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'canteen', label: 'Canteen' },
  { id: 'misc', label: 'Misc bill' },
  { id: 'inpatient', label: 'Inpatient stay' },
  { id: 'append', label: 'Append to stay' },
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

function PatientSearch({ patientId, setPatientId, label = 'Patient' }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState([]);
  const [selected, setSelected] = useState(null);

  const search = async () => {
    if (!q.trim()) return;
    try {
      const { data } = await axios.get('/api/patients/', { params: { search: q.trim(), limit: 10 } });
      const list = Array.isArray(data) ? data : (data?.patients || data?.items || []);
      setHits(list);
    } catch {
      try {
        const { data } = await axios.post('/api/patients/search?page=1&per_page=10', {
          search_term: q.trim(),
          sort_by: 'name',
          sort_order: 'asc',
        });
        setHits(data?.patients || []);
      } catch {
        setHits([]);
      }
    }
  };

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex gap-2">
        <Input
          placeholder="Search name / phone / MRN"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), search())}
        />
        <Button type="button" variant="outline" onClick={search}>Search</Button>
      </div>
      {hits.length > 0 && (
        <div className="border rounded-md max-h-40 overflow-auto text-sm">
          {hits.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`w-full text-left px-3 py-2 hover:bg-slate-100 ${patientId === p.id ? 'bg-blue-50' : ''}`}
              onClick={() => {
                setPatientId(p.id);
                setSelected(p);
                setHits([]);
              }}
            >
              {p.first_name} {p.last_name} — {p.primary_phone || p.phone || ''} {p.mrn ? `(${p.mrn})` : ''}
            </button>
          ))}
        </div>
      )}
      {selected && (
        <p className="text-xs text-muted-foreground">
          Selected: {selected.first_name} {selected.last_name} (id {selected.id})
        </p>
      )}
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
  const [type, setType] = useState('consultation');
  const [dates, setDates] = useState(emptyDates());
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [nurses, setNurses] = useState([]);
  const [labTests, setLabTests] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [ancillaryServices, setAncillaryServices] = useState([]);
  const [canteenItems, setCanteenItems] = useState([]);
  const [packages, setPackages] = useState([]);

  const [patientId, setPatientId] = useState(null);
  const [doctorId, setDoctorId] = useState('');
  const [consultFee, setConsultFee] = useState('');
  const [regFee, setRegFee] = useState('0');
  const [selectedTests, setSelectedTests] = useState([]);
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
  const [foodOrders, setFoodOrders] = useState([]);
  const [pharmacyIpLines, setPharmacyIpLines] = useState([]);
  const [packageId, setPackageId] = useState('');
  const [packagePrice, setPackagePrice] = useState('');
  const [preview, setPreview] = useState(null);
  const [appendAdmissionId, setAppendAdmissionId] = useState('');

  const doctorById = (id) => doctors.find((d) => String(d.id) === String(id));
  const nurseById = (id) => nurses.find((n) => String(n.id) === String(id));
  const ipFeeForDoctor = (id) => parseFee(doctorById(id)?.inpatient_fee_inr);
  const consultFeeForDoctor = (id) => parseFee(doctorById(id)?.consultation_fee_inr);

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
    if (type === 'lab') {
      axios.get('/api/lab/tests').then((r) => {
        setLabTests(Array.isArray(r.data) ? r.data : (r.data?.tests || []));
      }).catch(() => setLabTests([]));
    }
    if (type === 'inpatient' || type === 'append') {
      Promise.all([
        axios.get('/api/inpatient/rooms').catch(() => ({ data: [] })),
        axios.get('/api/inpatient/nurses').catch(() => ({ data: [] })),
        axios.get('/api/inpatient/ancillary-services', { params: { active_only: true } }).catch(() => ({ data: [] })),
        axios.get('/api/inpatient/packages', { params: { active_only: true } }).catch(() => ({ data: [] })),
        axios.get('/api/canteen/items', { params: { active_only: true } }).catch(() => ({ data: [] })),
      ]).then(([roomRes, nurseRes, ancRes, pkgRes, foodRes]) => {
        setRooms(Array.isArray(roomRes.data) ? roomRes.data : (roomRes.data?.rooms || []));
        setNurses(Array.isArray(nurseRes.data) ? nurseRes.data : []);
        setAncillaryServices(Array.isArray(ancRes.data) ? ancRes.data : []);
        setPackages(Array.isArray(pkgRes.data) ? pkgRes.data : []);
        setCanteenItems(Array.isArray(foodRes.data) ? foodRes.data : (foodRes.data?.items || []));
      });
    }
  }, [type]);

  const selectConsultDoctor = (id) => {
    setDoctorId(id);
    const fee = consultFeeForDoctor(id);
    if (fee !== '') setConsultFee(fee);
  };

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

    const canteen_orders = foodOrders
      .filter((o) => o.items?.some((i) => i.item_name && i.unit_price !== ''))
      .map((o) => ({
        serve_date: o.serve_date || dates.service_date,
        notes: o.notes || null,
        items: o.items
          .filter((i) => i.item_name && i.unit_price !== '')
          .map((i) => ({
            item_id: i.item_id ? Number(i.item_id) : null,
            item_name: i.item_name,
            quantity: Number(i.quantity || 1),
            unit_price: Number(i.unit_price || 0),
          })),
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
      canteen_orders,
      pharmacy_lines,
      surgery_package_id: packageId ? Number(packageId) : null,
      surgery_package_price: packageId && packagePrice !== '' ? Number(packagePrice) : null,
      deposits: [],
    };
  };

  const submit = async () => {
    setSaving(true);
    try {
      let res;
      if (type === 'consultation') {
        if (!patientId || !doctorId) throw new Error('Patient and doctor are required');
        res = await axios.post('/api/admin/catch-up/consultation', {
          ...datesPayload(),
          patient_id: patientId,
          doctor_id: Number(doctorId),
          consultation_fee: Number(consultFee || 0),
          registration_fee: Number(regFee || 0),
        });
      } else if (type === 'lab') {
        if (!patientId || selectedTests.length === 0) throw new Error('Patient and at least one test required');
        res = await axios.post('/api/admin/catch-up/lab', {
          ...datesPayload(),
          patient_id: patientId,
          test_ids: selectedTests.map(Number),
          doctor_id: doctorId ? Number(doctorId) : null,
        });
      } else if (type === 'pharmacy') {
        if (!patientId) throw new Error('Patient is required for pharmacy catch-up');
        const items = lines
          .filter((l) => l.item_name && l.unit_price !== '')
          .map((l) => ({
            item_name: l.item_name,
            quantity: Number(l.quantity || 1),
            unit_price: Number(l.unit_price || 0),
          }));
        if (!items.length) throw new Error('Add at least one line');
        res = await axios.post('/api/admin/catch-up/pharmacy-sale', {
          ...datesPayload(),
          patient_id: patientId,
          items,
          affect_stock: affectStock,
        });
      } else if (type === 'canteen') {
        const items = lines
          .filter((l) => l.item_name && l.unit_price !== '')
          .map((l) => ({
            item_name: l.item_name,
            quantity: Number(l.quantity || 1),
            unit_price: Number(l.unit_price || 0),
          }));
        if (!items.length) throw new Error('Add at least one line');
        res = await axios.post('/api/admin/catch-up/canteen-sale', {
          ...datesPayload(),
          patient_id: patientId || null,
          items,
        });
      } else if (type === 'misc') {
        if (!patientId) throw new Error('Patient is required');
        const items = lines
          .filter((l) => l.item_name && l.unit_price !== '')
          .map((l) => ({
            item_name: l.item_name,
            quantity: Number(l.quantity || 1),
            unit_price: Number(l.unit_price || 0),
            item_type: 'misc',
          }));
        if (!items.length) throw new Error('Add at least one line');
        res = await axios.post('/api/admin/catch-up/misc-bill', {
          ...datesPayload(),
          patient_id: patientId,
          items,
        });
      } else if (type === 'inpatient') {
        if (!patientId || !admitDoctorId || !roomId) {
          throw new Error('Patient, admitting doctor, and room are required');
        }
        res = await axios.post('/api/admin/catch-up/inpatient-stay', buildIpPayload());
      } else if (type === 'append') {
        if (!appendAdmissionId) throw new Error('Catch-up admission ID is required');
        const ip = buildIpPayload();
        const payload = {
          ...datesPayload(),
          visits: ip.visits,
          ancillary: ip.ancillary,
          canteen_orders: ip.canteen_orders,
          pharmacy_lines: ip.pharmacy_lines,
        };
        if (!payload.visits.length && !payload.ancillary.length
            && !payload.canteen_orders.length && !payload.pharmacy_lines.length) {
          throw new Error('Add at least one charge to append');
        }
        res = await axios.post(
          `/api/admin/catch-up/inpatient/${Number(appendAdmissionId)}/append-charges`,
          payload,
        );
      }
      toast({
        title: 'Catch-up saved',
        description: res?.data?.bill_number
          ? `Bill ${res.data.bill_number} — ₹${res.data.total}`
          : `Total ₹${res?.data?.total ?? ''}`,
      });
      setDates(emptyDates());
      setLines([{ item_name: '', quantity: 1, unit_price: '' }]);
      setSelectedTests([]);
      setDoctorVisits([]);
      setNurseVisits([]);
      setAncillaryRows([]);
      setFoodOrders([]);
      setPharmacyIpLines([]);
      setPackageId('');
      setPackagePrice('');
      setPreview(null);
      setAppendAdmissionId('');
      loadMeta();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : (detail?.message || err.message || 'Failed to save catch-up');
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    try {
      if (!roomId) throw new Error('Select a room first');
      const { data } = await axios.post('/api/admin/catch-up/inpatient-stay/preview', {
        ...buildIpPayload(),
        patient_id: patientId || 0,
        admitting_doctor_id: Number(admitDoctorId || doctors[0]?.id || 0),
      });
      setPreview(data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast({
        title: 'Preview failed',
        description: typeof detail === 'string' ? detail : err.message,
        variant: 'destructive',
      });
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
          {type !== 'canteen' && type !== 'append' && (
            <PatientSearch patientId={patientId} setPatientId={setPatientId} />
          )}
          {type === 'canteen' && (
            <PatientSearch
              patientId={patientId}
              setPatientId={setPatientId}
              label="Patient (optional — links to central bill)"
            />
          )}

          {type === 'consultation' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <Label>Doctor</Label>
                <select
                  className="w-full h-9 rounded-md border px-2 text-sm"
                  value={doctorId}
                  onChange={(e) => selectConsultDoctor(e.target.value)}
                >
                  <option value="">Select doctor</option>
                  {doctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.first_name} {d.last_name}
                      {d.consultation_fee_inr ? ` (₹${d.consultation_fee_inr})` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Consultation fee</Label>
                <Input type="number" min="0" step="0.01" value={consultFee} onChange={(e) => setConsultFee(e.target.value)} />
                {doctorId && consultFeeForDoctor(doctorId) !== '' && (
                  <p className="text-xs text-muted-foreground mt-1">
                    From doctor profile: ₹{consultFeeForDoctor(doctorId)}
                  </p>
                )}
              </div>
              <div>
                <Label>Registration fee</Label>
                <Input type="number" min="0" step="0.01" value={regFee} onChange={(e) => setRegFee(e.target.value)} />
              </div>
            </div>
          )}

          {type === 'lab' && (
            <div className="space-y-2">
              <Label>Lab tests</Label>
              <div className="border rounded-md max-h-48 overflow-auto p-2 space-y-1">
                {labTests.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedTests.includes(t.id)}
                      onChange={(e) => {
                        setSelectedTests((prev) =>
                          e.target.checked ? [...prev, t.id] : prev.filter((id) => id !== t.id)
                        );
                      }}
                    />
                    <span>{t.name} — ₹{t.cost}</span>
                  </label>
                ))}
                {labTests.length === 0 && (
                  <p className="text-xs text-muted-foreground">No lab tests found</p>
                )}
              </div>
              <div>
                <Label>Ordering doctor (optional)</Label>
                <select
                  className="w-full h-9 rounded-md border px-2 text-sm"
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                >
                  <option value="">None</option>
                  {doctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.first_name} {d.last_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {['pharmacy', 'canteen', 'misc'].includes(type) && (
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
                    <Input type="number" min="1" value={l.quantity} onChange={(e) => updateLine(idx, 'quantity', e.target.value)} />
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
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={affectStock} onChange={(e) => setAffectStock(e.target.checked)} />
                  Deduct pharmacy stock (requires batch ids via API — leave off for financial-only catch-up)
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
                      <Input
                        type="number"
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
                title="Food orders"
                onAdd={() => setFoodOrders((p) => [...p, {
                  serve_date: dates.service_date,
                  items: [{ item_id: '', item_name: '', quantity: 1, unit_price: '' }],
                }])}
              >
                {foodOrders.length === 0 && (
                  <p className="text-xs text-muted-foreground">No food orders added</p>
                )}
                {foodOrders.map((o, oIdx) => (
                  <div key={oIdx} className="border rounded p-2 space-y-2 bg-slate-50">
                    <div className="flex gap-2 items-end">
                      <div className="flex-1">
                        <Label className="text-xs">Serve date</Label>
                        <Input
                          type="date"
                          value={o.serve_date}
                          onChange={(e) => setFoodOrders((p) => p.map((x, i) => i === oIdx ? { ...x, serve_date: e.target.value } : x))}
                        />
                      </div>
                      <Button type="button" size="sm" variant="outline" onClick={() => {
                        setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                          ...x,
                          items: [...x.items, { item_id: '', item_name: '', quantity: 1, unit_price: '' }],
                        } : x));
                      }}>
                        <Plus className="h-3 w-3 mr-1" /> Item
                      </Button>
                      <Button type="button" size="icon" variant="ghost" onClick={() => setFoodOrders((p) => p.filter((_, i) => i !== oIdx))}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    {o.items.map((li, liIdx) => (
                      <div key={liIdx} className="grid grid-cols-12 gap-2">
                        <div className="col-span-5">
                          <select
                            className="w-full h-9 rounded-md border px-2 text-sm"
                            value={li.item_id || ''}
                            onChange={(e) => {
                              const id = e.target.value;
                              const cat = canteenItems.find((c) => String(c.id) === String(id));
                              setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                                ...x,
                                items: x.items.map((it, j) => j === liIdx ? {
                                  ...it,
                                  item_id: id,
                                  item_name: cat?.name || it.item_name,
                                  unit_price: cat ? String(cat.price) : it.unit_price,
                                } : it),
                              } : x));
                            }}
                          >
                            <option value="">Catalog / custom</option>
                            {canteenItems.map((c) => (
                              <option key={c.id} value={c.id}>{c.name} — ₹{c.price}</option>
                            ))}
                          </select>
                        </div>
                        <div className="col-span-3">
                          <Input
                            placeholder="Item name"
                            value={li.item_name}
                            onChange={(e) => setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                              ...x,
                              items: x.items.map((it, j) => j === liIdx ? { ...it, item_name: e.target.value } : it),
                            } : x))}
                          />
                        </div>
                        <div className="col-span-1">
                          <Input
                            type="number"
                            min="1"
                            value={li.quantity}
                            onChange={(e) => setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                              ...x,
                              items: x.items.map((it, j) => j === liIdx ? { ...it, quantity: e.target.value } : it),
                            } : x))}
                          />
                        </div>
                        <div className="col-span-2">
                          <Input
                            type="number"
                            min="0"
                            step="0.01"
                            placeholder="Price"
                            value={li.unit_price}
                            onChange={(e) => setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                              ...x,
                              items: x.items.map((it, j) => j === liIdx ? { ...it, unit_price: e.target.value } : it),
                            } : x))}
                          />
                        </div>
                        <div className="col-span-1">
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            onClick={() => setFoodOrders((p) => p.map((x, i) => i === oIdx ? {
                              ...x,
                              items: x.items.filter((_, j) => j !== liIdx),
                            } : x))}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
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
                      <Input
                        type="number"
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

              {type === 'inpatient' && (
              <div className="flex gap-2 flex-wrap items-center">
                <Button type="button" variant="outline" onClick={runPreview}>Preview charges</Button>
                {preview && (
                  <p className="text-sm">
                    {preview.stay_days}d room ₹{preview.room_total}
                    {' + '}visits ₹{preview.visit_total}
                    {' + '}anc ₹{preview.ancillary_total}
                    {' + '}food ₹{preview.food_total}
                    {' + '}meds ₹{preview.pharmacy_total || 0}
                    {' + '}pkg ₹{preview.package_total || 0}
                    {' → '}<strong>₹{preview.grand_total}</strong>
                  </p>
                )}
              </div>
              )}
            </div>
          )}

          <div className="pt-2">
            <Button onClick={submit} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {type === 'append' ? 'Append & re-finalize' : 'Save catch-up'}
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
    </div>
  );
};

export default CatchUpBills;
