import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '../../../../components/ui/dialog';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../../components/ui/tabs';
import { Loader2 } from 'lucide-react';
import DischargePrintBar from './DischargePrintBar';
import DischargeSummaryEditor from '../DischargeSummaryEditor';
import { printPdfFromUrl } from '../../../../utils/printPdf';

const summaryIsReady = (status) => status === 'ready' || status === 'locked';

const Field = ({ label, value }) => (
  <div>
    <div className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</div>
    <div className="text-sm whitespace-pre-wrap">{value || '—'}</div>
  </div>
);

const DischargedAdmissionDetailDialog = ({
  open,
  onClose,
  admissionId,
  doctorsList = [],
  canWriteSummary = false,
}) => {
  const [loading, setLoading] = useState(false);
  const [admission, setAdmission] = useState(null);
  const [summary, setSummary] = useState(null);
  const [visits, setVisits] = useState([]);
  const [vitals, setVitals] = useState([]);
  const [showSummaryEditor, setShowSummaryEditor] = useState(false);

  const load = useCallback(async () => {
    if (!admissionId || !open) return;
    setLoading(true);
    try {
      const opts = (url) => axios.get(url).then(r => r.data).catch(() => null);
      const [adm, sum, vis, vit] = await Promise.all([
        opts(`/api/inpatient/admissions/${admissionId}`),
        opts(`/api/inpatient/admissions/${admissionId}/discharge-summary`),
        opts(`/api/inpatient/admissions/${admissionId}/visits`),
        opts(`/api/inpatient/admissions/${admissionId}/vitals?limit=30`),
      ]);
      setAdmission(adm);
      setSummary(sum);
      setVisits(vis?.items || (Array.isArray(vis) ? vis : []));
      setVitals(vit?.items || (Array.isArray(vit) ? vit : []));
    } finally {
      setLoading(false);
    }
  }, [admissionId, open]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!open) {
      setAdmission(null);
      setSummary(null);
      setVisits([]);
      setVitals([]);
      setShowSummaryEditor(false);
    }
  }, [open]);

  const formatDt = (d) => {
    if (!d) return '—';
    try { return new Date(d).toLocaleString(); } catch { return d; }
  };

  const ready = summaryIsReady(summary?.status);

  return (
    <>
      <Dialog open={open} onOpenChange={v => !v && onClose?.()}>
        <DialogContent className="max-w-3xl max-h-[92vh] flex flex-col overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              {admission?.patient_name || 'Admission details'}
              {admission?.admission_number && (
                <span className="text-sm font-normal text-gray-500">{admission.admission_number}</span>
              )}
              {admission?.status && (
                <Badge variant="outline" className="capitalize">{admission.status}</Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          {loading ? (
            <div className="py-12 text-center text-gray-500">
              <Loader2 className="h-6 w-6 mx-auto animate-spin" />
            </div>
          ) : !admission ? (
            <p className="text-sm text-gray-500 py-8 text-center">Admission not found.</p>
          ) : (
            <div className="flex flex-col min-h-0 flex-1 gap-3">
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant="outline">
                  Room {admission.room_number || '—'}
                  {admission.bed_label ? ` / ${admission.bed_label}` : ''}
                </Badge>
                <Badge variant="outline" className="capitalize">{admission.admission_type || '—'}</Badge>
                {admission.discharge_type && (
                  <Badge variant="outline" className="capitalize">
                    {(admission.discharge_type || '').replace(/_/g, ' ')}
                  </Badge>
                )}
              </div>

              <DischargePrintBar
                canPrintFinalBill={admission.status === 'discharged'}
                canPrintDischargeSummary={ready}
                canPrintGatePass={admission.status === 'discharged'}
                onPrintFinalBill={() => printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/bill/pdf`)}
                onPrintDischargeSummary={() => printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/discharge-summary/pdf`)}
                onPrintGatePass={() => printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/gate-pass/pdf`)}
                onPrintDetailedSummary={() => printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/admission-detail/pdf`)}
              />

              <div className="flex flex-wrap gap-2">
                {(canWriteSummary || ready) && (
                  <Button size="sm" variant="outline" onClick={() => setShowSummaryEditor(true)}>
                    {canWriteSummary && summary?.status !== 'locked' ? 'Open discharge summary' : 'View discharge summary'}
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={load}>Refresh</Button>
              </div>

              <Tabs defaultValue="overview" className="flex-1 min-h-0 flex flex-col">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="summary">Summary</TabsTrigger>
                  <TabsTrigger value="visits">Visits ({visits.length})</TabsTrigger>
                  <TabsTrigger value="vitals">Vitals ({vitals.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="mt-3 space-y-3 overflow-y-auto max-h-[50vh] text-sm">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Admitted" value={formatDt(admission.admission_date)} />
                    <Field label="Discharged" value={formatDt(admission.discharge_date)} />
                    <Field label="Admission reason" value={admission.admission_reason} />
                    <Field label="Condition on discharge" value={admission.condition_on_discharge} />
                  </div>
                  <Field label="Admission notes" value={admission.admission_notes} />
                </TabsContent>

                <TabsContent value="summary" className="mt-3 space-y-3 overflow-y-auto max-h-[50vh] text-sm">
                  {!summary ? (
                    <p className="text-gray-500 text-sm">No discharge summary on file.</p>
                  ) : (
                    <>
                      <Badge className={
                        summary.status === 'ready' ? 'bg-green-100 text-green-800'
                          : summary.status === 'locked' ? 'bg-slate-100 text-slate-700'
                            : 'bg-amber-100 text-amber-800'
                      }>
                        {summary.status === 'ready' ? 'Ready to print'
                          : summary.status === 'locked' ? 'Finalized' : 'Draft'}
                      </Badge>
                      <Field label="Primary diagnosis" value={summary.primary_diagnosis} />
                      <Field label="Provisional diagnosis" value={summary.provisional_diagnosis} />
                      <Field label="Course in hospital" value={summary.course_in_hospital} />
                      <Field label="Discharge advice" value={summary.discharge_advice} />
                      <Field label="Follow up" value={summary.follow_up} />
                    </>
                  )}
                </TabsContent>

                <TabsContent value="visits" className="mt-3 overflow-y-auto max-h-[50vh]">
                  {visits.length === 0 ? (
                    <p className="text-sm text-gray-500">No visits recorded.</p>
                  ) : (
                    <div className="space-y-2">
                      {visits.map(v => (
                        <div key={v.id} className="border rounded p-2 text-xs">
                          <div className="flex justify-between font-medium">
                            <span>{(v.visit_type || '').replace(/_/g, ' ')}</span>
                            <span className="text-gray-400">{formatDt(v.visit_datetime)}</span>
                          </div>
                          {v.notes && <p className="mt-1 text-gray-700 whitespace-pre-wrap">{v.notes}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="vitals" className="mt-3 overflow-y-auto max-h-[50vh]">
                  {vitals.length === 0 ? (
                    <p className="text-sm text-gray-500">No vitals recorded.</p>
                  ) : (
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-gray-50 border-b">
                          <th className="text-left p-1.5">When</th>
                          <th className="text-left p-1.5">BP</th>
                          <th className="text-left p-1.5">Pulse</th>
                          <th className="text-left p-1.5">Temp</th>
                          <th className="text-left p-1.5">SpO₂</th>
                        </tr>
                      </thead>
                      <tbody>
                        {vitals.map(v => (
                          <tr key={v.id} className="border-b">
                            <td className="p-1.5">{formatDt(v.recorded_at)}</td>
                            <td className="p-1.5">{v.blood_pressure || '—'}</td>
                            <td className="p-1.5">{v.pulse ?? '—'}</td>
                            <td className="p-1.5">{v.temperature ?? '—'}</td>
                            <td className="p-1.5">{v.spo2 ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <DischargeSummaryEditor
        open={showSummaryEditor}
        onClose={() => { setShowSummaryEditor(false); load(); }}
        admissionId={admissionId}
        admissionLabel={admission?.patient_name}
        doctorsList={doctorsList}
        readOnly={!canWriteSummary || summary?.status === 'locked'}
        onSaved={() => load()}
      />
    </>
  );
};

export default DischargedAdmissionDetailDialog;
