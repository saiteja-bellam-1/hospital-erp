import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import {
  Banknote, Shield, FileCheck2, Landmark,
  CheckCircle2, XCircle, Clock, Loader2, History, ArrowRightLeft,
  Stethoscope, UserCheck, UserPlus
} from 'lucide-react';

const SCHEME_ICONS = {
  cash:              Banknote,
  private_insurance: Shield,
  tpa:               FileCheck2,
  govt_scheme:       Landmark,
};

const SchemeIcon = ({ type, className }) => {
  const I = SCHEME_ICONS[type] || Banknote;
  return <I className={className} />;
};

const AdmissionDetailHeader = ({
  admission,
  doctorsList = [],
  canAccept = false,
  canConvertPayer = false,
  onChanged,
}) => {
  const { toast } = useToast();

  // Local copy of acceptance bits so the banner reflects optimistic updates
  // without needing the parent to re-fetch the whole admission.
  const [acceptanceStatus, setAcceptanceStatus] = useState(admission?.acceptance_status || 'accepted');
  const [acceptDialogOpen, setAcceptDialogOpen] = useState(false);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [acceptingDoctorId, setAcceptingDoctorId] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Change payer dialog state
  const [payerDialogOpen, setPayerDialogOpen] = useState(false);
  const [schemes, setSchemes] = useState([]);
  const [payerForm, setPayerForm] = useState({
    payer_scheme_id: '', reason: '',
    scheme_member_id: '', scheme_approval_status: 'none',
    scheme_approval_ref: '', scheme_approval_amount: '',
  });

  // Payer history (toggleable inline panel)
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Keep local acceptance in sync with prop
  useEffect(() => {
    setAcceptanceStatus(admission?.acceptance_status || 'accepted');
  }, [admission?.id, admission?.acceptance_status]);

  const fetchHistory = useCallback(async () => {
    if (!admission?.id) return;
    setHistoryLoading(true);
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admission.id}/payer-history`);
      setHistory(res.data || []);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [admission?.id]);

  const fetchSchemes = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/payer-schemes',
        { params: { active_only: true } });
      setSchemes(res.data || []);
    } catch { setSchemes([]); }
  }, []);

  const openPayerDialog = () => {
    fetchSchemes();
    setPayerForm({
      payer_scheme_id: '', reason: '',
      scheme_member_id: admission?.scheme_member_id || '',
      scheme_approval_status: 'none',
      scheme_approval_ref: '',
      scheme_approval_amount: '',
    });
    setPayerDialogOpen(true);
  };

  const openHistory = async () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next) await fetchHistory();
  };

  const submitAccept = async () => {
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${admission.id}/accept`, {
        accepting_doctor_id: acceptingDoctorId ? parseInt(acceptingDoctorId, 10) : null,
      });
      setAcceptanceStatus('accepted');
      toast({ title: 'Admission accepted' });
      setAcceptDialogOpen(false);
      onChanged?.();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
              description: err.response?.data?.detail || 'Failed to accept' });
    } finally { setSubmitting(false); }
  };

  const submitReject = async () => {
    if (!rejectReason.trim()) {
      toast({ variant: 'destructive', title: 'Reason required' });
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${admission.id}/reject`, {
        reason: rejectReason.trim(),
      });
      setAcceptanceStatus('rejected');
      toast({ title: 'Admission rejected' });
      setRejectDialogOpen(false);
      onChanged?.();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
              description: err.response?.data?.detail || 'Failed to reject' });
    } finally { setSubmitting(false); }
  };

  const submitPayerChange = async () => {
    if (!payerForm.payer_scheme_id) {
      toast({ variant: 'destructive', title: 'Select new payer scheme' });
      return;
    }
    if (!payerForm.reason.trim()) {
      toast({ variant: 'destructive', title: 'Reason required',
              description: 'Why are you changing the payer mid-stay?' });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        payer_scheme_id: parseInt(payerForm.payer_scheme_id, 10),
        reason: payerForm.reason.trim(),
        scheme_member_id: payerForm.scheme_member_id || null,
        scheme_approval_status: payerForm.scheme_approval_status || null,
        scheme_approval_ref: payerForm.scheme_approval_ref || null,
        scheme_approval_amount: payerForm.scheme_approval_amount
          ? parseFloat(payerForm.scheme_approval_amount) : null,
      };
      await axios.patch(`/api/inpatient/admissions/${admission.id}/payer`, payload);
      toast({ title: 'Payer changed',
              description: 'Future charges go to the new payer.' });
      setPayerDialogOpen(false);
      // Refresh history if it's open
      if (historyOpen) fetchHistory();
      onChanged?.();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
              description: err.response?.data?.detail || 'Could not change payer' });
    } finally { setSubmitting(false); }
  };

  if (!admission) return null;

  const referringDisplay = admission.referring_doctor_name
    ? admission.referring_doctor_name
    : admission.referring_external_name
      ? `${admission.referring_external_name} (external)`
      : '—';

  const attendingDisplay = admission.attending_physician_id
    ? (doctorsList.find(d => d.id === admission.attending_physician_id)
        ? `${doctorsList.find(d => d.id === admission.attending_physician_id).first_name} ${doctorsList.find(d => d.id === admission.attending_physician_id).last_name}`
        : `User #${admission.attending_physician_id}`)
    : '—';

  const selectedNewScheme = schemes.find(s => s.id === parseInt(payerForm.payer_scheme_id, 10));

  return (
    <div className="space-y-2 px-4 pt-3 pb-2 border-b bg-gray-50">
      {/* Acceptance banner — only visible if pending or rejected */}
      {acceptanceStatus === 'pending' && (
        <div className="flex items-start gap-2 bg-amber-100 border-l-4 border-amber-500 rounded p-3">
          <Clock className="h-5 w-5 text-amber-700 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-900">Awaiting IP doctor acceptance.</p>
            <p className="text-xs text-amber-800">
              Clinical actions (vitals, MAR, visits, I/O) are locked until accepted.
            </p>
          </div>
          {canAccept && (
            <div className="flex gap-1">
              <Button size="sm" className="bg-green-600 hover:bg-green-700"
                      onClick={() => {
                        setAcceptingDoctorId(String(admission.attending_physician_id
                          || admission.admitting_doctor_id || ''));
                        setAcceptDialogOpen(true);
                      }}>
                <CheckCircle2 className="h-4 w-4 mr-1" /> Accept
              </Button>
              <Button size="sm" variant="outline" className="text-red-600"
                      onClick={() => setRejectDialogOpen(true)}>
                <XCircle className="h-4 w-4 mr-1" /> Reject
              </Button>
            </div>
          )}
        </div>
      )}

      {acceptanceStatus === 'rejected' && (
        <div className="flex items-start gap-2 bg-red-50 border-l-4 border-red-500 rounded p-3">
          <XCircle className="h-5 w-5 text-red-600 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-900">Admission rejected.</p>
            {admission.rejection_reason && (
              <p className="text-xs text-red-800">Reason: {admission.rejection_reason}</p>
            )}
            <p className="text-xs text-red-700 mt-0.5">Re-admit the patient if needed.</p>
          </div>
        </div>
      )}

      {/* Doctors row */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-gray-500 flex items-center gap-1">
            <UserCheck className="h-3 w-3" /> Referring
          </div>
          <div className="font-medium text-gray-800 truncate" title={referringDisplay}>
            {referringDisplay}
          </div>
        </div>
        <div>
          <div className="text-gray-500 flex items-center gap-1">
            <UserPlus className="h-3 w-3" /> Admitting / joining
          </div>
          <div className="font-medium text-gray-800 truncate">
            {admission.doctor_name || '—'}
          </div>
        </div>
        <div>
          <div className="text-gray-500 flex items-center gap-1">
            <Stethoscope className="h-3 w-3" /> Attending (under)
          </div>
          <div className="font-medium text-gray-800 truncate">
            {attendingDisplay}
          </div>
        </div>
      </div>

      {/* Payer chip + change + history toggle */}
      <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Payer:</span>
          {admission.payer_scheme_name ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-blue-50 border border-blue-200 text-xs">
              <SchemeIcon type={admission.payer_type} className="h-3.5 w-3.5 text-blue-600" />
              <span className="font-medium text-blue-900">{admission.payer_scheme_name}</span>
              {admission.scheme_approval_status && admission.scheme_approval_status !== 'none' && (
                <Badge className={`text-[10px] h-4 px-1 ml-1 ${
                  admission.scheme_approval_status === 'approved' ? 'bg-green-100 text-green-800' :
                  admission.scheme_approval_status === 'rejected' ? 'bg-red-100 text-red-800' :
                  admission.scheme_approval_status === 'disconnected' ? 'bg-orange-100 text-orange-800' :
                  'bg-yellow-100 text-yellow-800'
                }`}>
                  {admission.scheme_approval_status}
                </Badge>
              )}
              {admission.scheme_approval_amount != null && (
                <span className="text-blue-700 ml-1">
                  ₹{Number(admission.scheme_approval_amount).toFixed(0)}
                </span>
              )}
            </span>
          ) : (
            <span className="text-xs text-gray-400 italic">none set</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" className="h-7 text-xs"
                  onClick={openHistory}>
            <History className="h-3.5 w-3.5 mr-1" />
            {historyOpen ? 'Hide history' : 'View history'}
          </Button>
          {canConvertPayer && admission.status === 'admitted' && (
            <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={openPayerDialog}>
              <ArrowRightLeft className="h-3.5 w-3.5 mr-1" /> Change payer
            </Button>
          )}
        </div>
      </div>

      {/* History inline panel */}
      {historyOpen && (
        <div className="border rounded bg-white p-2 text-xs">
          {historyLoading ? (
            <div className="flex items-center gap-2 text-gray-500 py-1">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading…
            </div>
          ) : history.length === 0 ? (
            <p className="text-gray-500 italic">No payer changes yet.</p>
          ) : (
            <ul className="space-y-1">
              {history.map(h => (
                <li key={h.id} className="border-l-2 border-blue-300 pl-2">
                  <div>
                    <b>{h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}</b>
                    {' — '}
                    <span className="text-gray-600">
                      {h.from_scheme_name || h.from_payer_type || 'none'}
                    </span>
                    <span className="mx-1">→</span>
                    <span className="text-gray-800 font-medium">
                      {h.to_scheme_name || h.to_payer_type}
                    </span>
                  </div>
                  <div className="text-gray-600 italic">
                    "{h.reason}"
                    {h.changed_by_name && <span className="text-gray-400"> — by {h.changed_by_name}</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Accept dialog */}
      <Dialog open={acceptDialogOpen} onOpenChange={setAcceptDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Accept admission</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div><b>Patient:</b> {admission.patient_name}</div>
            <div>
              <Label>Accepting doctor *</Label>
              <Select value={acceptingDoctorId}
                      onValueChange={v => setAcceptingDoctorId(v)}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      Dr. {d.first_name} {d.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAcceptDialogOpen(false)}>Cancel</Button>
            <Button onClick={submitAccept} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Accept
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Reject admission</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-gray-700">
              Patient must be re-admitted from scratch after rejection.
            </p>
            <div>
              <Label>Reason *</Label>
              <Textarea rows={3} value={rejectReason}
                        onChange={e => setRejectReason(e.target.value)}
                        placeholder="e.g. Wrong specialty — transfer to general medicine." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={submitReject} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change payer dialog */}
      <Dialog open={payerDialogOpen} onOpenChange={setPayerDialogOpen}>
        <DialogContent className="max-w-lg max-h-[88vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Change payer mid-stay</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="text-sm bg-gray-50 border rounded p-2">
              <b>Current:</b> {admission.payer_scheme_name || '—'}
              {admission.scheme_member_id && <> · {admission.scheme_member_id}</>}
              {admission.scheme_approval_status && admission.scheme_approval_status !== 'none' &&
                ` (${admission.scheme_approval_status})`}
            </div>
            <div>
              <Label>New payer *</Label>
              <div className="grid grid-cols-3 gap-2 mt-1">
                {schemes
                  .filter(s => s.id !== admission.payer_scheme_id)
                  .map(s => {
                    const I = SCHEME_ICONS[s.scheme_type] || Banknote;
                    const selected = parseInt(payerForm.payer_scheme_id, 10) === s.id;
                    return (
                      <button key={s.id} type="button"
                              className={'border-2 rounded p-2 text-left flex flex-col gap-0.5 transition ' +
                                (selected
                                  ? 'border-blue-500 bg-blue-50'
                                  : 'border-gray-200 hover:border-gray-400')}
                              onClick={() => setPayerForm(p => ({ ...p, payer_scheme_id: String(s.id) }))}>
                        <I className={'h-4 w-4 ' + (selected ? 'text-blue-600' : 'text-gray-500')} />
                        <span className="text-xs font-medium">{s.name}</span>
                      </button>
                    );
                  })}
              </div>
            </div>
            {selectedNewScheme && selectedNewScheme.scheme_type !== 'cash' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Member / Policy ID</Label>
                  <Input value={payerForm.scheme_member_id}
                         onChange={e => setPayerForm(p => ({ ...p, scheme_member_id: e.target.value }))} />
                </div>
                <div>
                  <Label>Approval status</Label>
                  <Select value={payerForm.scheme_approval_status}
                          onValueChange={v => setPayerForm(p => ({ ...p, scheme_approval_status: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Not submitted</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="approved">Approved</SelectItem>
                      <SelectItem value="rejected">Rejected</SelectItem>
                      <SelectItem value="disconnected">Disconnected</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Approval ref</Label>
                  <Input value={payerForm.scheme_approval_ref}
                         onChange={e => setPayerForm(p => ({ ...p, scheme_approval_ref: e.target.value }))} />
                </div>
                <div>
                  <Label>Approved amount (₹)</Label>
                  <Input type="number" min="0" step="0.01"
                         value={payerForm.scheme_approval_amount}
                         onChange={e => setPayerForm(p => ({ ...p, scheme_approval_amount: e.target.value }))} />
                </div>
              </div>
            )}
            <div>
              <Label>Reason for change *</Label>
              <Textarea rows={3} value={payerForm.reason}
                        onChange={e => setPayerForm(p => ({ ...p, reason: e.target.value }))}
                        placeholder="e.g. Aarogyasri approval rejected — switching to private insurance." />
            </div>
            <div className="text-xs text-gray-600 bg-blue-50 border border-blue-200 rounded p-2">
              ℹ Future charges go to the new payer.
              Already-finalised bill splits remain on the previous payer.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPayerDialogOpen(false)}>Cancel</Button>
            <Button onClick={submitPayerChange} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Change payer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdmissionDetailHeader;
