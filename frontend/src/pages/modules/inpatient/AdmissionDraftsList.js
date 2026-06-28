import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import { Label } from '../../../components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { FileEdit, Loader2, PlayCircle, XCircle } from 'lucide-react';

const AdmissionDraftsList = ({ onResume, onChanged }) => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchDrafts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/admissions', {
        params: { status: 'draft', limit: 200 },
      });
      setRows(res.data?.items || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDrafts(); }, [fetchDrafts]);

  const submitCancel = async () => {
    if (!cancelTarget) return;
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${cancelTarget.id}/cancel`, {
        reason: cancelReason.trim() || null,
      });
      toast({
        title: 'Draft cancelled',
        description: `${cancelTarget.admission_number} was marked cancelled and the bed released.`,
      });
      setCancelTarget(null);
      setCancelReason('');
      fetchDrafts();
      onChanged?.();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Could not cancel draft';
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
          <p className="text-sm mt-2">Loading admission drafts…</p>
        </CardContent>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500 text-sm">
          <FileEdit className="h-6 w-6 mx-auto text-gray-400 mb-2" />
          No saved admission drafts. Use <b>Save draft</b> in the admit wizard to resume later.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {rows.map(adm => {
          const bedHeld = !!(adm.bed_id || adm.bed_number || adm.bed_label);
          return (
            <Card key={adm.id} className="border-slate-300">
              <CardContent className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <FileEdit className="h-4 w-4 text-slate-600" />
                      <span className="font-semibold text-sm">{adm.patient_name || '—'}</span>
                      <Badge className="bg-slate-100 text-slate-800 text-xs">Draft</Badge>
                      {bedHeld && (
                        <Badge className="bg-blue-100 text-blue-800 text-xs">Bed held</Badge>
                      )}
                      {adm.admission_type === 'emergency' && (
                        <Badge className="bg-red-100 text-red-800 text-xs">
                          ER{adm.triage_level ? ` T${adm.triage_level}` : ''}
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      {adm.room_number || 'Room TBD'}
                      {(adm.bed_label || adm.bed_number)
                        ? ` / ${adm.bed_label || adm.bed_number}` : ''}
                      {' · '}{adm.admission_number}
                      {adm.admission_date && (
                        <> · started {new Date(adm.admission_date).toLocaleString()}</>
                      )}
                    </div>
                    <div className="text-xs text-gray-600 mt-0.5">
                      {adm.doctor_name && <>Admitting: <b>{adm.doctor_name}</b></>}
                      {adm.payer_scheme_name && (
                        <> · Payer: <b>{adm.payer_scheme_name}</b></>
                      )}
                    </div>
                    {adm.admission_reason && (
                      <p className="text-xs text-gray-700 mt-1">
                        <span className="font-medium">Reason:</span> {adm.admission_reason}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 shrink-0">
                    <Button
                      size="sm"
                      className="bg-blue-600 hover:bg-blue-700"
                      onClick={() => onResume?.(adm)}
                    >
                      <PlayCircle className="h-4 w-4 mr-1" /> Resume
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => setCancelTarget(adm)}
                    >
                      <XCircle className="h-4 w-4 mr-1" /> Cancel
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Dialog open={!!cancelTarget} onOpenChange={v => !v && setCancelTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel admission draft</DialogTitle>
          </DialogHeader>
          {cancelTarget && (
            <div className="space-y-3">
              <p className="text-sm text-gray-700">
                <b>{cancelTarget.patient_name}</b> ({cancelTarget.admission_number}) will be
                marked <b>cancelled</b> and kept on record. Any held bed will be released.
              </p>
              <div>
                <Label>Reason (optional)</Label>
                <Textarea
                  rows={3}
                  value={cancelReason}
                  onChange={e => setCancelReason(e.target.value)}
                  placeholder="e.g. Patient chose outpatient care instead."
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)}>Keep draft</Button>
            <Button variant="destructive" onClick={submitCancel} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Cancel draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AdmissionDraftsList;
