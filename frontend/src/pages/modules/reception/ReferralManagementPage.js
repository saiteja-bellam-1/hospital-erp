import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { Textarea } from '../../../components/ui/textarea';
import { useToast } from '../../../hooks/use-toast';
import axios from 'axios';
import {
  Users, Plus, Search, Edit2, Trash2, Phone, MapPin, Eye, Loader2,
  DollarSign, ArrowLeft, Stethoscope, TestTube
} from 'lucide-react';

const ReferralManagementPage = () => {
  const { toast } = useToast();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [referrals, setReferrals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Form dialog
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', phone: '', village: '', mandal: '', district: '' });
  const [saving, setSaving] = useState(false);

  // Detail view
  const [selectedReferral, setSelectedReferral] = useState(null);
  const [details, setDetails] = useState(null);
  const [, setDetailsLoading] = useState(false);

  // Commission form
  const [showCommForm, setShowCommForm] = useState(false);
  const [commForm, setCommForm] = useState({ amount: '', payment_method: 'cash', notes: '' });
  const [commSaving, setCommSaving] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchReferrals(); }, []);

  const fetchReferrals = async () => {
    try {
      const res = await axios.get('/api/referrals/all', { headers });
      setReferrals(res.data);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load referrals' });
    } finally {
      setLoading(false);
    }
  };

  const openForm = (ref = null) => {
    if (ref) {
      setEditing(ref);
      setForm({ name: ref.name, phone: ref.phone || '', village: ref.village || '', mandal: ref.mandal || '', district: ref.district || '' });
    } else {
      setEditing(null);
      setForm({ name: '', phone: '', village: '', mandal: '', district: '' });
    }
    setShowForm(true);
  };

  const saveReferral = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`/api/referrals/${editing.id}`, form, { headers });
        toast({ title: 'Updated' });
      } else {
        await axios.post('/api/referrals', form, { headers });
        toast({ title: 'Added' });
      }
      setShowForm(false);
      fetchReferrals();
      if (selectedReferral && editing?.id === selectedReferral.id) fetchDetails(editing.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to save' });
    } finally { setSaving(false); }
  };

  const deleteReferral = async (id) => {
    if (!window.confirm('Deactivate this referral?')) return;
    try {
      await axios.delete(`/api/referrals/${id}`, { headers });
      toast({ title: 'Deactivated' });
      fetchReferrals();
      if (selectedReferral?.id === id) { setSelectedReferral(null); setDetails(null); }
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to deactivate' });
    }
  };

  const reactivate = async (ref) => {
    try {
      await axios.put(`/api/referrals/${ref.id}`, { is_active: true }, { headers });
      toast({ title: 'Reactivated' });
      fetchReferrals();
    } catch {
      toast({ variant: 'destructive', title: 'Error' });
    }
  };

  const fetchDetails = async (id) => {
    setDetailsLoading(true);
    try {
      const res = await axios.get(`/api/referrals/${id}/details`, { headers });
      setDetails(res.data);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load details' });
    } finally { setDetailsLoading(false); }
  };

  const openDetails = (ref) => {
    setSelectedReferral(ref);
    fetchDetails(ref.id);
  };

  const addCommission = async () => {
    if (!commForm.amount || parseFloat(commForm.amount) <= 0) return;
    setCommSaving(true);
    try {
      await axios.post(`/api/referrals/${selectedReferral.id}/commissions`, {
        amount: parseFloat(commForm.amount),
        payment_method: commForm.payment_method,
        notes: commForm.notes || null,
      }, { headers });
      toast({ title: 'Commission recorded' });
      setShowCommForm(false);
      setCommForm({ amount: '', payment_method: 'cash', notes: '' });
      fetchDetails(selectedReferral.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setCommSaving(false); }
  };

  const deleteCommission = async (commId) => {
    if (!window.confirm('Delete this commission record?')) return;
    try {
      await axios.delete(`/api/referrals/${selectedReferral.id}/commissions/${commId}`, { headers });
      toast({ title: 'Deleted' });
      fetchDetails(selectedReferral.id);
    } catch {
      toast({ variant: 'destructive', title: 'Error' });
    }
  };

  const formatCurrency = (v) => `₹${Number(v || 0).toLocaleString('en-IN')}`;
  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const filtered = referrals.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return r.name.toLowerCase().includes(q) || (r.village || '').toLowerCase().includes(q) ||
      (r.mandal || '').toLowerCase().includes(q) || (r.phone || '').includes(q);
  });

  if (loading) return <div className="flex items-center justify-center p-12"><Loader2 className="w-6 h-6 animate-spin" /></div>;

  // ===== DETAIL VIEW =====
  if (selectedReferral && details) {
    const s = details.summary;
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => { setSelectedReferral(null); setDetails(null); }}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{details.referral.name}</h1>
            <p className="text-sm text-gray-500">
              {[details.referral.village, details.referral.mandal, details.referral.district].filter(Boolean).join(', ')}
              {details.referral.phone && <span> | {details.referral.phone}</span>}
            </p>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Consultations</p>
            <p className="text-xl font-bold">{s.total_consultations}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Lab Orders</p>
            <p className="text-xl font-bold">{s.total_lab_orders}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Total Revenue</p>
            <p className="text-xl font-bold text-blue-600">{formatCurrency(s.total_revenue)}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Commission Paid</p>
            <p className="text-xl font-bold text-green-600">{formatCurrency(s.total_commission_paid)}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Balance</p>
            <p className="text-xl font-bold text-orange-600">{formatCurrency(s.commission_balance)}</p>
          </CardContent></Card>
        </div>

        {/* Consultations */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Stethoscope className="h-4 w-4" /> Consultation Bills ({details.consultations.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {details.consultations.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">No consultation bills</p>
            ) : (
              <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                {details.consultations.map(b => (
                  <div key={b.id} className="p-2.5 flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium">{b.patient_name}</p>
                      <p className="text-xs text-gray-400">{b.reference} | {b.doctor_name} | {formatDate(b.date)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{formatCurrency(b.amount)}</p>
                      <Badge className={`text-[10px] ${b.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>{b.status}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Lab Orders */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <TestTube className="h-4 w-4" /> Lab Order Bills ({details.lab_orders.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {details.lab_orders.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">No lab order bills</p>
            ) : (
              <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                {details.lab_orders.map(b => (
                  <div key={b.id} className="p-2.5 flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium">{b.patient_name}</p>
                      <p className="text-xs text-gray-400">{b.test_name} | {b.reference} | {formatDate(b.date)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{formatCurrency(b.amount)}</p>
                      <Badge className={`text-[10px] ${b.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>{b.status}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Commission Payments */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <DollarSign className="h-4 w-4" /> Commission Payments ({details.commissions.length})
              </CardTitle>
              <Button size="sm" onClick={() => setShowCommForm(true)}>
                <Plus className="h-3 w-3 mr-1" /> Pay Commission
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {details.commissions.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">No commission payments recorded</p>
            ) : (
              <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                {details.commissions.map(c => (
                  <div key={c.id} className="p-2.5 flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium text-green-700">{formatCurrency(c.amount)}</p>
                      <p className="text-xs text-gray-400">
                        {formatDate(c.payment_date)} | {c.payment_method} | by {c.paid_by}
                        {c.notes && <span> | {c.notes}</span>}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-red-400" onClick={() => deleteCommission(c.id)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Commission Payment Dialog */}
        <Dialog open={showCommForm} onOpenChange={setShowCommForm}>
          <DialogContent className="max-w-sm">
            <DialogHeader><DialogTitle>Pay Commission — {selectedReferral.name}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div>
                <Label>Amount *</Label>
                <Input type="number" step="0.01" value={commForm.amount}
                  onChange={(e) => setCommForm({ ...commForm, amount: e.target.value })} placeholder="Enter amount" />
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select value={commForm.payment_method} onValueChange={(v) => setCommForm({ ...commForm, payment_method: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea value={commForm.notes} onChange={(e) => setCommForm({ ...commForm, notes: e.target.value })}
                  placeholder="Optional notes" rows={2} />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCommForm(false)}>Cancel</Button>
                <Button onClick={addCommission} disabled={!commForm.amount || commSaving}>
                  {commSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Record Payment
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ===== LIST VIEW =====
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Referral Management</h1>
          <p className="text-muted-foreground text-sm">Manage referrals, view bills, and track commissions</p>
        </div>
        <Button onClick={() => openForm()}>
          <Plus className="h-4 w-4 mr-1" /> Add Referral
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input placeholder="Search by name, village, mandal..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="pl-10" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(ref => (
          <Card key={ref.id} className={`cursor-pointer hover:shadow-md transition-shadow ${!ref.is_active ? 'opacity-50' : ''}`}
            onClick={() => ref.is_active && openDetails(ref)}>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h3 className="font-semibold text-base">{ref.name}</h3>
                  {ref.phone && (
                    <p className="text-sm text-gray-500 flex items-center gap-1 mt-0.5">
                      <Phone className="h-3 w-3" /> {ref.phone}
                    </p>
                  )}
                </div>
                {!ref.is_active && <Badge variant="secondary">Inactive</Badge>}
              </div>
              {(ref.village || ref.mandal || ref.district) && (
                <p className="text-xs text-gray-500 flex items-center gap-1 mb-3">
                  <MapPin className="h-3 w-3 flex-shrink-0" />
                  {[ref.village, ref.mandal, ref.district].filter(Boolean).join(', ')}
                </p>
              )}
              <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openDetails(ref)}>
                  <Eye className="h-3 w-3 mr-1" /> View
                </Button>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openForm(ref)}>
                  <Edit2 className="h-3 w-3 mr-1" /> Edit
                </Button>
                {ref.is_active ? (
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-red-500" onClick={() => deleteReferral(ref.id)}>
                    <Trash2 className="h-3 w-3 mr-1" /> Deactivate
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-green-600" onClick={() => reactivate(ref)}>
                    Reactivate
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full text-center py-12 text-gray-500">
            <Users className="h-10 w-10 mx-auto mb-2 text-gray-300" />
            <p>No referrals found. Click "Add Referral" to create one.</p>
          </div>
        )}
      </div>

      {/* Add/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Referral' : 'Add Referral'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Person name" />
            </div>
            <div>
              <Label>Phone</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone number" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Village</Label><Input value={form.village} onChange={(e) => setForm({ ...form, village: e.target.value })} placeholder="Village" /></div>
              <div><Label>Mandal</Label><Input value={form.mandal} onChange={(e) => setForm({ ...form, mandal: e.target.value })} placeholder="Mandal" /></div>
              <div><Label>District</Label><Input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} placeholder="District" /></div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button onClick={saveReferral} disabled={!form.name.trim() || saving}>
                {saving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} {editing ? 'Update' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReferralManagementPage;
