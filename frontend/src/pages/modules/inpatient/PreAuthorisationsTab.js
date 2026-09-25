import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { ConfirmDialog } from '../../../components/ui/confirm-dialog';
import { useToast } from '../../../hooks/use-toast';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import { errorDetail } from '../../../utils/apiErrors';
import { Plus, Trash2, Upload, Download, Paperclip } from 'lucide-react';

const STATUS_COLOR = {
  requested: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  expansion_requested: 'bg-yellow-100 text-yellow-800',
  expanded: 'bg-purple-100 text-purple-800',
  expired: 'bg-gray-100 text-gray-800',
};

const BLANK_REQUEST = {
  patient_id: '',
  admission_id: '',
  insurance_provider: '',
  policy_number: '',
  tpa_id: '',
  requested_amount: '',
  notes: '',
};

const inr = (n) => `₹${Number(n || 0).toFixed(2)}`;

const pendingExpansion = (p) => {
  const rows = [...(p.expansions || [])];
  return rows.reverse().find((e) => e.status === 'requested') || null;
};

const docFileName = (path) => (path || 'preauth-document').split('/').pop();

export default function PreAuthorisationsTab({ canManage = false }) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);
  const uploadIdRef = useRef(null);

  const [preauths, setPreauths] = useState([]);
  const [preauthSearch, setPreauthSearch] = useState('');
  const [preauthStatusFilter, setPreauthStatusFilter] = useState('');
  const [tpaList, setTpaList] = useState([]);
  const [loading, setLoading] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(BLANK_REQUEST);
  const [selectedPatient, setSelectedPatient] = useState(null);

  const [active, setActive] = useState(null);
  const [showDecision, setShowDecision] = useState(false);
  const [decisionForm, setDecisionForm] = useState({
    status: 'approved',
    approved_amount: '',
    validity_days: '',
    approval_reference: '',
    notes: '',
  });

  const [showExpansion, setShowExpansion] = useState(false);
  const [expansionForm, setExpansionForm] = useState({ requested_amount: '', reason: '' });

  const [showExpansionDecision, setShowExpansionDecision] = useState(false);
  const [expansionDecisionForm, setExpansionDecisionForm] = useState({
    status: 'approved',
    approved_amount: '',
  });
  const [pendingExp, setPendingExp] = useState(null);

  const [confirmState, setConfirmState] = useState({ open: false });

  const fetchTpaList = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/tpa', { params: { active_only: true } });
      setTpaList(res.data || []);
    } catch {
      setTpaList([]);
    }
  }, []);

  const fetchPreauths = useCallback(async () => {
    try {
      const params = preauthStatusFilter ? { status: preauthStatusFilter } : {};
      const res = await axios.get('/api/inpatient/preauth', { params });
      let data = res.data || [];
      if (preauthSearch) {
        const q = preauthSearch.toLowerCase();
        data = data.filter((p) =>
          (p.patient_name || '').toLowerCase().includes(q)
          || (p.insurance_provider || '').toLowerCase().includes(q)
          || (p.tpa_name || '').toLowerCase().includes(q)
        );
      }
      setPreauths(data);
    } catch {
      setPreauths([]);
    }
  }, [preauthStatusFilter, preauthSearch]);

  useEffect(() => {
    fetchPreauths();
  }, [fetchPreauths]);

  useEffect(() => {
    fetchTpaList();
  }, [fetchTpaList]);

  const fail = (err, fallback) => {
    toast({ variant: 'destructive', title: 'Error', description: errorDetail(err, fallback) });
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!selectedPatient) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick a patient' });
      return;
    }
    setLoading(true);
    try {
      await axios.post('/api/inpatient/preauth', {
        patient_id: selectedPatient.id,
        admission_id: createForm.admission_id ? parseInt(createForm.admission_id, 10) : null,
        insurance_provider: createForm.insurance_provider,
        policy_number: createForm.policy_number || null,
        tpa_id: createForm.tpa_id ? parseInt(createForm.tpa_id, 10) : null,
        requested_amount: parseFloat(createForm.requested_amount),
        notes: createForm.notes || null,
      });
      toast({ title: 'Pre-authorisation requested' });
      setShowCreate(false);
      setCreateForm(BLANK_REQUEST);
      setSelectedPatient(null);
      fetchPreauths();
    } catch (err) {
      fail(err, 'Failed to submit request');
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/preauth/${active.id}/decision`, {
        status: decisionForm.status,
        approved_amount: decisionForm.approved_amount ? parseFloat(decisionForm.approved_amount) : null,
        validity_days: decisionForm.validity_days ? parseInt(decisionForm.validity_days, 10) : null,
        approval_reference: decisionForm.approval_reference || null,
        notes: decisionForm.notes || null,
      });
      toast({ title: 'Decision recorded' });
      setShowDecision(false);
      fetchPreauths();
    } catch (err) {
      fail(err, 'Failed to record decision');
    } finally {
      setLoading(false);
    }
  };

  const handleExpansion = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/preauth/${active.id}/expansion-request`, {
        requested_amount: parseFloat(expansionForm.requested_amount),
        reason: expansionForm.reason || null,
      });
      toast({ title: 'Expansion requested' });
      setShowExpansion(false);
      fetchPreauths();
    } catch (err) {
      fail(err, 'Failed to request expansion');
    } finally {
      setLoading(false);
    }
  };

  const handleExpansionDecision = async (e) => {
    e.preventDefault();
    if (!pendingExp) return;
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/preauth/expansions/${pendingExp.id}/decision`, {
        status: expansionDecisionForm.status,
        approved_amount: expansionDecisionForm.approved_amount
          ? parseFloat(expansionDecisionForm.approved_amount)
          : null,
      });
      toast({ title: 'Expansion decision recorded' });
      setShowExpansionDecision(false);
      fetchPreauths();
    } catch (err) {
      fail(err, 'Failed to record expansion decision');
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (preauthId, file) => {
    if (!file || !preauthId) return;
    if (file.size > 10 * 1024 * 1024) {
      toast({ variant: 'destructive', title: 'File too large', description: 'Max 10MB' });
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(`/api/inpatient/preauth/${preauthId}/upload-document`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast({ title: 'Document uploaded' });
      fetchPreauths();
    } catch (err) {
      fail(err, 'Upload failed');
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDownload = async (p) => {
    try {
      const res = await axios.get(`/api/inpatient/preauth/${p.id}/document`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = docFileName(p.approval_document_path);
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Download failed', description: errorDetail(err, 'Download failed') });
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`/api/inpatient/preauth/${id}`);
      toast({ title: 'Pre-authorisation deleted' });
      fetchPreauths();
    } catch (err) {
      fail(err, 'Failed to delete');
    }
  };

  return (
    <div className="p-6 overflow-y-auto h-full space-y-4">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"
        onChange={(e) => {
          const file = e.target.files?.[0];
          const id = uploadIdRef.current;
          if (file && id) handleUpload(id, file);
        }}
      />

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Insurance Pre-Authorisations</h2>
        {canManage && (
          <Button onClick={() => {
            setCreateForm(BLANK_REQUEST);
            setSelectedPatient(null);
            setShowCreate(true);
          }}>
            <Plus className="h-4 w-4 mr-2" /> New Request
          </Button>
        )}
      </div>

      <div className="flex gap-3">
        <Input
          className="max-w-xs"
          placeholder="Search by patient, provider, TPA..."
          value={preauthSearch}
          onChange={(e) => setPreauthSearch(e.target.value)}
        />
        <Select
          value={preauthStatusFilter || 'all'}
          onValueChange={(v) => setPreauthStatusFilter(v === 'all' ? '' : v)}
        >
          <SelectTrigger className="max-w-[200px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="requested">Requested</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
            <SelectItem value="expansion_requested">Expansion Requested</SelectItem>
            <SelectItem value="expanded">Expanded</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {preauths.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-gray-500">No pre-authorisation requests.</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {preauths.map((p) => {
            const pending = pendingExpansion(p);
            const canDelete = ['requested', 'rejected', 'expired'].includes(p.status);
            const canExpand = p.status === 'approved' || p.status === 'expanded';
            return (
              <Card key={p.id}>
                <CardContent className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm">{p.patient_name || '—'}</span>
                        <Badge className={`text-xs ${STATUS_COLOR[p.status] || 'bg-gray-100 text-gray-800'}`}>{p.status.replace(/_/g, ' ')}</Badge>
                        <span className="text-xs text-gray-500">{p.insurance_provider}</span>
                        {p.tpa_name && <span className="text-xs text-gray-500">· TPA: {p.tpa_name}</span>}
                      </div>
                      <div className="text-xs text-gray-600 mt-1">
                        Requested {inr(p.requested_amount)}
                        {p.approved_amount > 0 && <> · Approved {inr(p.approved_amount)}</>}
                        {p.policy_number && <> · Policy {p.policy_number}</>}
                        {p.approval_reference && <> · Ref {p.approval_reference}</>}
                        {p.validity_days ? <> · {p.validity_days} days</> : null}
                        · {new Date(p.request_date).toLocaleDateString()}
                      </div>
                      {p.admission_number && <div className="text-xs text-gray-500">Admission {p.admission_number}</div>}
                      {p.notes && <p className="text-xs italic text-gray-600 mt-1">{p.notes}</p>}
                      {p.approval_document_path && (
                        <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                          <Paperclip className="h-3 w-3" />
                          <span className="truncate">{docFileName(p.approval_document_path)}</span>
                        </div>
                      )}
                      {(p.expansions || []).length > 0 && (
                        <div className="mt-2 space-y-1">
                          {p.expansions.map((e) => (
                            <div key={e.id} className="text-xs text-gray-500">
                              Expansion {e.status}: {inr(e.requested_amount)}
                              {e.approved_amount > 0 && <> · approved {inr(e.approved_amount)}</>}
                              {e.reason ? <> · {e.reason}</> : null}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1 justify-end shrink-0">
                      {canManage && p.status === 'requested' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActive(p);
                            setDecisionForm({
                              status: 'approved',
                              approved_amount: String(p.requested_amount),
                              validity_days: '',
                              approval_reference: '',
                              notes: '',
                            });
                            setShowDecision(true);
                          }}
                        >
                          Record Decision
                        </Button>
                      )}
                      {canManage && p.status === 'expansion_requested' && pending && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActive(p);
                            setPendingExp(pending);
                            setExpansionDecisionForm({
                              status: 'approved',
                              approved_amount: String(pending.requested_amount),
                            });
                            setShowExpansionDecision(true);
                          }}
                        >
                          Record Expansion
                        </Button>
                      )}
                      {canManage && canExpand && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActive(p);
                            setExpansionForm({ requested_amount: '', reason: '' });
                            setShowExpansion(true);
                          }}
                        >
                          Request Expansion
                        </Button>
                      )}
                      {canManage && (
                        <Button
                          size="sm"
                          variant="outline"
                          title="Upload approval letter"
                          onClick={() => {
                            uploadIdRef.current = p.id;
                            fileInputRef.current?.click();
                          }}
                        >
                          <Upload className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      {p.approval_document_path && (
                        <Button
                          size="sm"
                          variant="outline"
                          title="Download document"
                          onClick={() => handleDownload(p)}
                        >
                          <Download className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      {canManage && canDelete && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-red-500"
                          title="Delete"
                          onClick={() => setConfirmState({
                            open: true,
                            title: 'Delete pre-authorisation?',
                            message: `Delete the ${p.status} request for ${p.patient_name || 'this patient'}?`,
                            onConfirm: () => {
                              setConfirmState({ open: false });
                              handleDelete(p.id);
                            },
                          })}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={(open) => { setShowCreate(open); if (!open) setSelectedPatient(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>New Pre-Authorisation Request</DialogTitle></DialogHeader>
          <form onSubmit={handleCreate} className="space-y-3">
            <PatientSearchPicker
              value={selectedPatient}
              onChange={setSelectedPatient}
              label="Patient"
              required
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Insurance Provider *</Label>
                <Input
                  value={createForm.insurance_provider}
                  onChange={(e) => setCreateForm((p) => ({ ...p, insurance_provider: e.target.value }))}
                  required
                  placeholder="e.g. Star Health"
                />
              </div>
              <div>
                <Label>Policy Number</Label>
                <Input
                  value={createForm.policy_number}
                  onChange={(e) => setCreateForm((p) => ({ ...p, policy_number: e.target.value }))}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>TPA</Label>
                <Select
                  value={createForm.tpa_id || 'none'}
                  onValueChange={(v) => setCreateForm((p) => ({ ...p, tpa_id: v === 'none' ? '' : v }))}
                >
                  <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {tpaList.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>{t.tpa_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Requested Amount (₹) *</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={createForm.requested_amount}
                  onChange={(e) => setCreateForm((p) => ({ ...p, requested_amount: e.target.value }))}
                  required
                />
              </div>
            </div>
            <div>
              <Label>Admission (if any)</Label>
              <Input
                value={createForm.admission_id}
                onChange={(e) => setCreateForm((p) => ({ ...p, admission_id: e.target.value }))}
                placeholder="Admission ID (numeric)"
              />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea
                value={createForm.notes}
                onChange={(e) => setCreateForm((p) => ({ ...p, notes: e.target.value }))}
                rows={2}
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Submit Request'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={showDecision} onOpenChange={setShowDecision}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Insurer Decision</DialogTitle></DialogHeader>
          {active && (
            <form onSubmit={handleDecision} className="space-y-3">
              <p className="text-sm">{active.insurance_provider} · Requested {inr(active.requested_amount)}</p>
              <div>
                <Label>Decision *</Label>
                <Select value={decisionForm.status} onValueChange={(v) => setDecisionForm((p) => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {decisionForm.status === 'approved' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Approved Amount (₹) *</Label>
                      <Input
                        type="number"
                        step="0.01"
                        value={decisionForm.approved_amount}
                        onChange={(e) => setDecisionForm((p) => ({ ...p, approved_amount: e.target.value }))}
                        required
                      />
                    </div>
                    <div>
                      <Label>Validity (days)</Label>
                      <Input
                        type="number"
                        value={decisionForm.validity_days}
                        onChange={(e) => setDecisionForm((p) => ({ ...p, validity_days: e.target.value }))}
                      />
                    </div>
                  </div>
                  <div>
                    <Label>Approval Reference</Label>
                    <Input
                      value={decisionForm.approval_reference}
                      onChange={(e) => setDecisionForm((p) => ({ ...p, approval_reference: e.target.value }))}
                    />
                  </div>
                </>
              )}
              <div>
                <Label>Notes</Label>
                <Textarea
                  value={decisionForm.notes}
                  onChange={(e) => setDecisionForm((p) => ({ ...p, notes: e.target.value }))}
                  rows={2}
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Decision'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showExpansion} onOpenChange={setShowExpansion}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Request Amount Expansion</DialogTitle></DialogHeader>
          {active && (
            <form onSubmit={handleExpansion} className="space-y-3">
              <p className="text-sm">
                {active.insurance_provider} · Currently approved {inr(active.approved_amount)}
              </p>
              <div>
                <Label>Additional Amount (₹) *</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={expansionForm.requested_amount}
                  onChange={(e) => setExpansionForm((p) => ({ ...p, requested_amount: e.target.value }))}
                  required
                />
              </div>
              <div>
                <Label>Reason</Label>
                <Textarea
                  value={expansionForm.reason}
                  onChange={(e) => setExpansionForm((p) => ({ ...p, reason: e.target.value }))}
                  rows={2}
                  placeholder="e.g. Extended stay, additional procedure"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Submit Expansion'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showExpansionDecision} onOpenChange={setShowExpansionDecision}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Expansion Decision</DialogTitle></DialogHeader>
          {active && pendingExp && (
            <form onSubmit={handleExpansionDecision} className="space-y-3">
              <p className="text-sm">
                {active.insurance_provider} · Extra requested {inr(pendingExp.requested_amount)}
                {pendingExp.reason ? ` · ${pendingExp.reason}` : ''}
              </p>
              <div>
                <Label>Decision *</Label>
                <Select
                  value={expansionDecisionForm.status}
                  onValueChange={(v) => setExpansionDecisionForm((p) => ({ ...p, status: v }))}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {expansionDecisionForm.status === 'approved' && (
                <div>
                  <Label>Approved Extra Amount (₹) *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={expansionDecisionForm.approved_amount}
                    onChange={(e) => setExpansionDecisionForm((p) => ({ ...p, approved_amount: e.target.value }))}
                    required
                  />
                </div>
              )}
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Decision'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        onConfirm={confirmState.onConfirm}
        onCancel={() => setConfirmState({ open: false })}
      />
    </div>
  );
}
