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
  Stethoscope, UserCheck, UserPlus, Plus, Paperclip, Download, Ban,
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

  // Scheme approval ledger
  const [approvalsOpen, setApprovalsOpen] = useState(false);
  const [approvals, setApprovals] = useState([]);
  const [approvalsTotal, setApprovalsTotal] = useState(0);
  const [approvalsLoading, setApprovalsLoading] = useState(false);
  const [addApprovalOpen, setAddApprovalOpen] = useState(false);
  const [approvalForm, setApprovalForm] = useState({
    amount: '', approval_reference: '', notes: '', file: null,
  });

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

  const fetchApprovals = useCallback(async () => {
    if (!admission?.id) return;
    setApprovalsLoading(true);
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admission.id}/scheme-approvals`);
      setApprovals(res.data?.items || []);
      setApprovalsTotal(Number(res.data?.total_approved || 0));
    } catch {
      setApprovals([]);
      setApprovalsTotal(0);
    } finally {
      setApprovalsLoading(false);
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

  const openApprovals = async () => {
    const next = !approvalsOpen;
    setApprovalsOpen(next);
    if (next) await fetchApprovals();
  };

  const openAddApproval = () => {
    setApprovalForm({ amount: '', approval_reference: '', notes: '', file: null });
    setAddApprovalOpen(true);
  };

  const submitAddApproval = async () => {
    const amt = parseFloat(approvalForm.amount);
    if (!amt || amt <= 0) {
      toast({ variant: 'destructive', title: 'Enter a valid approved amount' });
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('amount', String(amt));
      if (approvalForm.approval_reference.trim()) {
        fd.append('approval_reference', approvalForm.approval_reference.trim());
      }
      if (approvalForm.notes.trim()) {
        fd.append('notes', approvalForm.notes.trim());
      }
      if (approvalForm.file) {
        fd.append('file', approvalForm.file);
      }
      await axios.post(`/api/inpatient/admissions/${admission.id}/scheme-approvals`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast({ title: 'Approval added', description: `₹${amt.toLocaleString('en-IN')} credited as deposit.` });
      setAddApprovalOpen(false);
      setApprovalsOpen(true);
      await fetchApprovals();
      onChanged?.();
    } catch (err) {
      toast({
        variant: 'destructive', title: 'Error',
        description: err.response?.data?.detail || 'Could not add approval',
      });
    } finally { setSubmitting(false); }
  };

  const downloadApprovalDoc = async (item) => {
    try {
      const res = await axios.get(
        `/api/inpatient/scheme-approvals/${item.id}/document`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = item.document_name || 'approval-document';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ variant: 'destructive', title: 'Download failed' });
    }
  };

  const voidApproval = async (item) => {
    const reason = window.prompt('Reason to void this approval?');
    if (!reason || !reason.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/scheme-approvals/${item.id}/void`, {
        reason: reason.trim(),
      });
      toast({ title: 'Approval voided' });
      await fetchApprovals();
      onChanged?.();
    } catch (err) {
      toast({
        variant: 'destructive', title: 'Error',
        description: err.response?.data?.detail || 'Could not void',
      });
    } finally { setSubmitting(false); }
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
          {admission.payer_type && admission.payer_type !== 'cash' && (
            <Button size="sm" variant="ghost" className="h-7 text-xs"
                    onClick={openApprovals}>
              <FileCheck2 className="h-3.5 w-3.5 mr-1" />
              {approvalsOpen ? 'Hide approvals' : 'Approvals'}
            </Button>
          )}
          <Button size="sm" variant="ghost" className="h-7 text-xs"
                  onClick={openHistory}>
            <History className="h-3.5 w-3.5 mr-1" />
            {historyOpen ? 'Hide history' : 'View history'}
          </Button>
          {canConvertPayer && admission.status === 'admitted' && admission.payer_type &&
            admission.payer_type !== 'cash' && (
            <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={openAddApproval}>
              <Plus className="h-3.5 w-3.5 mr-1" /> Add approval
            </Button>
          )}
          {canConvertPayer && admission.status === 'admitted' && (
            <Button size="sm" variant="outline" className="h-7 text-xs"
                    onClick={openPayerDialog}>
              <ArrowRightLeft className="h-3.5 w-3.5 mr-1" /> Change payer
            </Button>
          )}
        </div>
      </div>

      {/* Approvals ledger panel */}
      {approvalsOpen && (
        <div className="border rounded bg-white p-2 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium text-gray-700">
              Scheme approvals
              {approvalsTotal > 0 && (
                <span className="ml-2 text-green-700">
                  Total ₹{approvalsTotal.toLocaleString('en-IN')}
                </span>
              )}
            </span>
            {canConvertPayer && admission.status === 'admitted' && (
              <Button size="sm" variant="ghost" className="h-6 text-xs"
                      onClick={openAddApproval}>
                <Plus className="h-3 w-3 mr-1" /> Add
              </Button>
            )}
          </div>
          {approvalsLoading ? (
            <div className="flex items-center gap-2 text-gray-500 py-1">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading…
            </div>
          ) : approvals.length === 0 ? (
            <p className="text-gray-500 italic">
              No approvals yet. Use &quot;Add approval&quot; when insurance/scheme credits more amount.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {approvals.map((a) => (
                <li key={a.id}
                    className="flex items-start justify-between gap-2 border-l-2 border-green-400 pl-2 py-0.5">
                  <div className="min-w-0">
                    <div className="font-semibold text-gray-800">
                      ₹{Number(a.amount).toLocaleString('en-IN')}
                      {a.approval_reference && (
                        <span className="font-normal text-gray-500 ml-1">
                          · ref {a.approval_reference}
                        </span>
                      )}
                    </div>
                    <div className="text-gray-500">
                      {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                      {a.created_by_name && ` — ${a.created_by_name}`}
                      {a.notes && <span className="italic"> · {a.notes}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {a.has_document && (
                      <Button type="button" size="sm" variant="ghost" className="h-6 w-6 p-0"
                              title={a.document_name || 'Download'}
                              onClick={() => downloadApprovalDoc(a)}>
                        <Download className="h-3.5 w-3.5 text-blue-600" />
                      </Button>
                    )}
                    {canConvertPayer && a.status === 'approved' && (
                      <Button type="button" size="sm" variant="ghost" className="h-6 w-6 p-0"
                              title="Void" disabled={submitting}
                              onClick={() => voidApproval(a)}>
                        <Ban className="h-3.5 w-3.5 text-red-500" />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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
                  <Label>Add approved amount (₹)</Label>
                  <Input type="number" min="0" step="0.01"
                         value={payerForm.scheme_approval_amount}
                         onChange={e => setPayerForm(p => ({ ...p, scheme_approval_amount: e.target.value }))} />
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    Posted as a credit deposit. Add more later via &quot;Add approval&quot;.
                  </p>
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

      {/* Add scheme approval (+ optional document) */}
      <Dialog open={addApprovalOpen} onOpenChange={setAddApprovalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add scheme approval</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-xs text-gray-600 bg-green-50 border border-green-200 rounded p-2">
              Each approval is added on top of previous ones and credited as a deposit.
            </p>
            <div>
              <Label>Approved amount (₹) *</Label>
              <Input type="number" min="0.01" step="0.01"
                     value={approvalForm.amount}
                     onChange={e => setApprovalForm(p => ({ ...p, amount: e.target.value }))} />
            </div>
            <div>
              <Label>Approval reference</Label>
              <Input value={approvalForm.approval_reference}
                     onChange={e => setApprovalForm(p => ({ ...p, approval_reference: e.target.value }))}
                     placeholder="Insurer / TPA auth number" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea rows={2} value={approvalForm.notes}
                        onChange={e => setApprovalForm(p => ({ ...p, notes: e.target.value }))}
                        placeholder="e.g. Expansion for ICU stay" />
            </div>
            <div>
              <Label className="flex items-center gap-1">
                <Paperclip className="h-3.5 w-3.5" /> Supporting document
              </Label>
              <Input type="file" accept=".pdf,image/*,.doc,.docx"
                     className="mt-1 text-xs"
                     onChange={e => setApprovalForm(p => ({
                       ...p, file: e.target.files?.[0] || null,
                     }))} />
              {approvalForm.file && (
                <p className="text-[10px] text-gray-500 mt-1 truncate">
                  {approvalForm.file.name}
                </p>
              )}
              <p className="text-[10px] text-gray-500 mt-0.5">
                Optional. PDF / image / Word, max 10MB.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddApprovalOpen(false)}>Cancel</Button>
            <Button onClick={submitAddApproval} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Add approval
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdmissionDetailHeader;
