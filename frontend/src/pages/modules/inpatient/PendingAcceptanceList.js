import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import { Label } from '../../../components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { CheckCircle2, XCircle, Loader2, Clock } from 'lucide-react';

const PendingAcceptanceList = ({
  doctorsList = [],
  canAccept = false,
  currentUserId = null,
  onChanged,
  onOpenDetail,
}) => {
  // Per-row override: even if the user lacks the static `accept_admission`
  // permission, they should be able to act on an admission where they are
  // the admitting / attending doctor — that's the IP-doctor on the case.
  const canAcceptThis = (adm) => canAccept ||
    (currentUserId && (adm.admitting_doctor_id === currentUserId
                       || adm.attending_physician_id === currentUserId));
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [acceptTarget, setAcceptTarget] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [acceptingDoctorId, setAcceptingDoctorId] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      // Backend list_admissions accepts a status filter; we ask for 'admitted'
      // and then filter client-side to acceptance_status='pending' since the
      // backend doesn't expose a dedicated filter (the queue is small).
      const res = await axios.get('/api/inpatient/admissions',
        { params: { status: 'admitted', limit: 200 } });
      const all = res.data?.items || res.data || [];
      setRows(all.filter(a => a.acceptance_status === 'pending'));
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPending(); }, [fetchPending]);

  const submitAccept = async () => {
    if (!acceptTarget) return;
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${acceptTarget.id}/accept`, {
        accepting_doctor_id: acceptingDoctorId ? parseInt(acceptingDoctorId, 10) : null,
      });
      toast({ title: 'Admission accepted',
              description: `${acceptTarget.patient_name} — clinical actions unlocked.` });
      setAcceptTarget(null);
      setAcceptingDoctorId('');
      fetchPending();
      onChanged?.();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not accept admission';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  const submitReject = async () => {
    if (!rejectTarget) return;
    if (!rejectReason.trim()) {
      toast({ variant: 'destructive', title: 'Reason required',
              description: 'Enter a rejection reason.' });
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${rejectTarget.id}/reject`, {
        reason: rejectReason.trim(),
      });
      toast({ title: 'Admission rejected',
              description: 'Patient must be re-admitted.' });
      setRejectTarget(null);
      setRejectReason('');
      fetchPending();
      onChanged?.();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not reject admission';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading pending admissions…</p>
        </CardContent>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500 text-sm">
          <CheckCircle2 className="h-6 w-6 mx-auto text-green-500 mb-2" />
          No admissions awaiting IP-doctor acceptance.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {rows.map(adm => (
          <Card key={adm.id} className="border-amber-300">
            <CardContent className="py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Clock className="h-4 w-4 text-amber-600" />
                    <span className="font-semibold text-sm">{adm.patient_name || '—'}</span>
                    <Badge className="bg-amber-100 text-amber-800 text-xs">Pending acceptance</Badge>
                    {adm.admission_type === 'emergency' && (
                      <Badge className="bg-red-100 text-red-800 text-xs">
                        ER{adm.triage_level ? ` T${adm.triage_level}` : ''}
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">
                    {adm.room_number} {(adm.bed_label || adm.bed_number)
                      ? `/ ${adm.bed_label || adm.bed_number}` : ''}
                    {' · '}{adm.admission_number}
                    {' · admitted '}
                    {adm.admission_date
                      ? new Date(adm.admission_date).toLocaleString()
                      : '—'}
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5">
                    Admitting: <b>{adm.doctor_name || '—'}</b>
                    {adm.referring_doctor_name && (
                      <> · Referring: <b>{adm.referring_doctor_name}</b></>
                    )}
                    {adm.referring_external_name && !adm.referring_doctor_name && (
                      <> · Referring (ext): <b>{adm.referring_external_name}</b></>
                    )}
                    {adm.payer_scheme_name && (
                      <> · Payer: <b>{adm.payer_scheme_name}</b>
                        {adm.scheme_approval_status && adm.scheme_approval_status !== 'none' &&
                          ` (${adm.scheme_approval_status})`}
                      </>
                    )}
                  </div>
                  {adm.admission_reason && (
                    <p className="text-xs text-gray-700 mt-1">
                      <span className="font-medium">Reason:</span> {adm.admission_reason}
                    </p>
                  )}
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  {onOpenDetail && (
                    <Button size="sm" variant="outline"
                            onClick={() => onOpenDetail(adm)}>
                      View detail
                    </Button>
                  )}
                  {canAcceptThis(adm) && (
                    <>
                      <Button size="sm" className="bg-green-600 hover:bg-green-700"
                              onClick={() => {
                                setAcceptTarget(adm);
                                setAcceptingDoctorId(String(adm.attending_physician_id
                                  || adm.admitting_doctor_id || ''));
                              }}>
                        <CheckCircle2 className="h-4 w-4 mr-1" /> Accept
                      </Button>
                      <Button size="sm" variant="outline"
                              className="text-red-600 hover:text-red-700"
                              onClick={() => setRejectTarget(adm)}>
                        <XCircle className="h-4 w-4 mr-1" /> Reject
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Accept dialog */}
      <Dialog open={!!acceptTarget} onOpenChange={v => !v && setAcceptTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Accept admission</DialogTitle>
          </DialogHeader>
          {acceptTarget && (
            <div className="space-y-3">
              <div className="text-sm">
                <div><b>Patient:</b> {acceptTarget.patient_name}</div>
                <div className="text-gray-600">
                  {acceptTarget.room_number}
                  {(acceptTarget.bed_label || acceptTarget.bed_number)
                    ? ` / ${acceptTarget.bed_label || acceptTarget.bed_number}` : ''}
                </div>
              </div>
              <div>
                <Label>Accepting doctor *</Label>
                <Select value={acceptingDoctorId}
                        onValueChange={v => setAcceptingDoctorId(v)}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
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
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAcceptTarget(null)}>Cancel</Button>
            <Button onClick={submitAccept} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Accept admission
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject dialog */}
      <Dialog open={!!rejectTarget} onOpenChange={v => !v && setRejectTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reject admission</DialogTitle>
          </DialogHeader>
          {rejectTarget && (
            <div className="space-y-3">
              <p className="text-sm text-gray-700">
                <b>{rejectTarget.patient_name}</b> will be marked rejected.
                The patient must be re-admitted from scratch.
              </p>
              <div>
                <Label>Reason *</Label>
                <Textarea rows={3}
                          value={rejectReason}
                          onChange={e => setRejectReason(e.target.value)}
                          placeholder="e.g. Wrong specialty — transfer to general medicine." />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={submitReject} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PendingAcceptanceList;
