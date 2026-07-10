import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { Plus, Trash2, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { localDateString } from '../../../utils/localDate';

const toIso = (d) => localDateString(d);
const SHIFT_LABELS = { morning: 'M', afternoon: 'A', night: 'N' };
const STATUS_CLASSES = {
  working: 'bg-green-100 text-green-800',
  on_call: 'bg-blue-100 text-blue-800',
  leave:   'bg-orange-100 text-orange-800',
  off:     'bg-gray-200 text-gray-700',
};

const DoctorRosterTab = ({
  doctorsList = [],
  weekStart,
  onShiftWeek,
  canManage = false,
}) => {
  const { toast } = useToast();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    doctor_id: '', roster_date: '', shift: 'morning',
    status: 'working', ward: '', notes: '',
  });
  const [saving, setSaving] = useState(false);

  const weekDates = useMemo(() => {
    const arr = [];
    const start = new Date(weekStart);
    for (let i = 0; i < 7; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [weekStart]);

  const fetchEntries = useCallback(async () => {
    if (!weekDates.length) return;
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/doctor-roster', {
        params: {
          start_date: toIso(weekDates[0]),
          end_date: toIso(weekDates[6]),
        },
      });
      setEntries(res.data || []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [weekDates]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  // Build a fast lookup: { [doctor_id]: { [yyyy-mm-dd]: { morning|afternoon|night: entry } } }
  const cells = useMemo(() => {
    const out = {};
    for (const e of entries) {
      const date = e.roster_date ? e.roster_date.slice(0, 10) : '';
      if (!out[e.doctor_id]) out[e.doctor_id] = {};
      if (!out[e.doctor_id][date]) out[e.doctor_id][date] = {};
      out[e.doctor_id][date][e.shift] = e;
    }
    return out;
  }, [entries]);

  const visibleDoctors = useMemo(() => {
    if (entries.length === 0) return doctorsList;
    const ids = new Set(entries.map(e => e.doctor_id));
    // include rostered doctors first, then everyone else
    const rostered = doctorsList.filter(d => ids.has(d.id));
    const others = doctorsList.filter(d => !ids.has(d.id));
    return [...rostered, ...others];
  }, [doctorsList, entries]);

  const openCellDialog = (doctor, date, shift) => {
    if (!canManage) return;
    const existing = cells[doctor.id]?.[toIso(date)]?.[shift];
    if (existing) {
      setEditing(existing);
      setForm({
        doctor_id: String(doctor.id),
        roster_date: toIso(date),
        shift,
        status: existing.status,
        ward: existing.ward || '',
        notes: existing.notes || '',
      });
    } else {
      setEditing(null);
      setForm({
        doctor_id: String(doctor.id),
        roster_date: toIso(date),
        shift,
        status: 'working', ward: '', notes: '',
      });
    }
    setDialogOpen(true);
  };

  const openAdd = () => {
    setEditing(null);
    setForm({
      doctor_id: '',
      roster_date: toIso(weekDates[0]),
      shift: 'morning',
      status: 'working', ward: '', notes: '',
    });
    setDialogOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.doctor_id || !form.roster_date) {
      toast({ variant: 'destructive', title: 'Missing fields' });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`/api/inpatient/doctor-roster/${editing.id}`, {
          shift: form.shift, status: form.status,
          ward: form.ward || null, notes: form.notes || null,
        });
        toast({ title: 'Updated' });
      } else {
        await axios.post('/api/inpatient/doctor-roster', {
          doctor_id: parseInt(form.doctor_id, 10),
          roster_date: form.roster_date,
          shift: form.shift,
          status: form.status,
          ward: form.ward || null,
          notes: form.notes || null,
        });
        toast({ title: 'Added' });
      }
      setDialogOpen(false);
      fetchEntries();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Save failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!editing) return;
    if (!window.confirm('Delete this roster entry?')) return;
    setSaving(true);
    try {
      await axios.delete(`/api/inpatient/doctor-roster/${editing.id}`);
      toast({ title: 'Deleted' });
      setDialogOpen(false);
      fetchEntries();
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Delete failed' });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => onShiftWeek?.(-7)}>
            <ChevronLeft className="h-4 w-4" /> Prev
          </Button>
          <span className="text-sm font-medium px-2">
            {weekDates[0]?.toLocaleDateString()} – {weekDates[6]?.toLocaleDateString()}
          </span>
          <Button size="sm" variant="outline" onClick={() => onShiftWeek?.(7)}>
            Next <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        {canManage && (
          <Button size="sm" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" /> Add entry
          </Button>
        )}
      </div>

      <p className="text-xs text-gray-500">
        Click any cell to assign / edit. M = morning · A = afternoon · N = night.
      </p>

      {loading ? (
        <Card><CardContent className="py-10 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" /> Loading…
        </CardContent></Card>
      ) : visibleDoctors.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-gray-500">
          No doctors on staff yet.
        </CardContent></Card>
      ) : (
        <div className="border rounded overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-2 text-left sticky left-0 bg-gray-50 border-r">Doctor</th>
                {weekDates.map(d => (
                  <th key={d.toISOString()} className="px-1 py-2 text-center border-r" colSpan={3}>
                    <div className="font-semibold">
                      {d.toLocaleDateString(undefined, { weekday: 'short' })}
                    </div>
                    <div className="text-gray-500">
                      {d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' })}
                    </div>
                  </th>
                ))}
              </tr>
              <tr className="bg-gray-100">
                <th className="px-2 py-1 sticky left-0 bg-gray-100 border-r"></th>
                {weekDates.map(d => (
                  <React.Fragment key={d.toISOString()}>
                    <th className="px-1 py-1 text-center text-[10px]">M</th>
                    <th className="px-1 py-1 text-center text-[10px]">A</th>
                    <th className="px-1 py-1 text-center text-[10px] border-r">N</th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleDoctors.map(doctor => (
                <tr key={doctor.id} className="border-t">
                  <td className="px-2 py-1 sticky left-0 bg-white border-r font-medium">
                    {doctor.first_name} {doctor.last_name}
                  </td>
                  {weekDates.map(d => (
                    <React.Fragment key={d.toISOString()}>
                      {['morning', 'afternoon', 'night'].map(shift => {
                        const cell = cells[doctor.id]?.[toIso(d)]?.[shift];
                        const cellClass = cell ? STATUS_CLASSES[cell.status] : 'hover:bg-blue-50';
                        return (
                          <td
                            key={shift}
                            onClick={() => openCellDialog(doctor, d, shift)}
                            className={`px-1 py-1 text-center cursor-pointer transition ${cellClass} ${
                              shift === 'night' ? 'border-r' : ''
                            }`}
                            title={cell ? `${cell.status}${cell.ward ? ' · ' + cell.ward : ''}` : 'Click to add'}
                          >
                            {cell
                              ? <span className="text-[10px] font-semibold">
                                  {SHIFT_LABELS[shift]}
                                  {cell.ward ? ' ' + cell.ward.slice(0, 3) : ''}
                                </span>
                              : <span className="text-gray-300">·</span>}
                          </td>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit roster entry' : 'Add roster entry'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <div>
              <Label>Doctor *</Label>
              <Select value={form.doctor_id}
                      onValueChange={v => setForm(p => ({ ...p, doctor_id: v }))}
                      disabled={!!editing}>
                <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      Dr. {d.first_name} {d.last_name}
                      {d.specialization ? ` · ${d.specialization}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Date *</Label>
                <Input type="date" value={form.roster_date}
                       onChange={e => setForm(p => ({ ...p, roster_date: e.target.value }))}
                       disabled={!!editing} />
              </div>
              <div>
                <Label>Shift *</Label>
                <Select value={form.shift}
                        onValueChange={v => setForm(p => ({ ...p, shift: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="morning">Morning (06–14)</SelectItem>
                    <SelectItem value="afternoon">Afternoon (14–22)</SelectItem>
                    <SelectItem value="night">Night (22–06)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Status *</Label>
                <Select value={form.status}
                        onValueChange={v => setForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="working">Working</SelectItem>
                    <SelectItem value="on_call">On-call</SelectItem>
                    <SelectItem value="leave">Leave</SelectItem>
                    <SelectItem value="off">Off</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Ward</Label>
                <Input value={form.ward}
                       onChange={e => setForm(p => ({ ...p, ward: e.target.value }))}
                       placeholder="e.g. ICU, Gen-W2" />
              </div>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea rows={2} value={form.notes}
                        onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} />
            </div>
            <DialogFooter className="flex items-center justify-between">
              <div>
                {editing && canManage && (
                  <Button type="button" variant="ghost" className="text-red-600"
                          onClick={remove} disabled={saving}>
                    <Trash2 className="h-4 w-4 mr-1" /> Delete
                  </Button>
                )}
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="outline"
                        onClick={() => setDialogOpen(false)}>Cancel</Button>
                <Button type="submit" disabled={saving || !canManage}>
                  {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  {editing ? 'Save' : 'Add'}
                </Button>
              </div>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};


// Side panel showing who is on duty right now
export const OnDutyNowPanel = () => {
  const [data, setData] = useState({ doctors: [], nurses: [], at: '', shift: '' });
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [docRes, nurseRes] = await Promise.all([
        axios.get('/api/inpatient/duty-doctor/on-duty').catch(() => ({ data: { on_duty: [] } })),
        // Nurse on-duty: needs target_date + shift; derive from doctor response if it's there,
        // otherwise compute locally.
        (async () => {
          const now = new Date();
          const hour = now.getHours();
          const shift = hour >= 6 && hour < 14 ? 'morning'
                      : hour >= 14 && hour < 22 ? 'afternoon' : 'night';
          // For night 00-06, the roster_date is "yesterday"
          let date = new Date(now);
          if (hour < 6) date.setDate(date.getDate() - 1);
          const iso = localDateString(date);
          return axios.get('/api/inpatient/roster/on-duty', {
            params: { target_date: iso, shift },
          }).catch(() => ({ data: [] }));
        })(),
      ]);
      setData({
        doctors: docRes.data?.on_duty || [],
        nurses: nurseRes.data || [],
        at: docRes.data?.at || new Date().toISOString(),
        shift: docRes.data?.shift || '',
      });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Card className="lg:sticky lg:top-4">
      <CardContent className="py-3 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Now on duty</h3>
          <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={load}>
            ↻ refresh
          </Button>
        </div>
        <p className="text-[10px] text-gray-500">
          {data.shift ? `${data.shift} shift` : ''}
          {data.at && ' · ' + new Date(data.at).toLocaleString()}
        </p>
        {loading ? (
          <div className="text-xs text-gray-500"><Loader2 className="h-3 w-3 animate-spin inline mr-1" /> loading…</div>
        ) : (
          <>
            <div>
              <p className="text-[11px] uppercase tracking-wide font-semibold text-gray-600 mt-1">Doctors</p>
              {data.doctors.length === 0
                ? <p className="text-xs text-gray-400 italic">— none —</p>
                : (
                  <ul className="text-xs space-y-0.5">
                    {data.doctors.map(d => (
                      <li key={d.doctor_id} className="flex items-center justify-between">
                        <span>{d.doctor_name}{d.ward ? ` · ${d.ward}` : ''}</span>
                        {d.status === 'on_call' &&
                          <Badge className="bg-blue-100 text-blue-700 text-[10px]">on-call</Badge>}
                      </li>
                    ))}
                  </ul>
                )}
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide font-semibold text-gray-600 mt-2">Nurses</p>
              {data.nurses.length === 0
                ? <p className="text-xs text-gray-400 italic">— none —</p>
                : (
                  <ul className="text-xs space-y-0.5">
                    {data.nurses.map(n => (
                      <li key={n.nurse_id} className="flex items-center justify-between">
                        <span>{n.nurse_name}{n.ward ? ` · ${n.ward}` : ''}</span>
                        {n.status === 'on_call' &&
                          <Badge className="bg-blue-100 text-blue-700 text-[10px]">on-call</Badge>}
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default DoctorRosterTab;
