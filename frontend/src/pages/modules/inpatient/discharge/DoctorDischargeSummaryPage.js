import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import { FileText, Loader2, Printer, Search } from 'lucide-react';
import DischargeSummaryEditor from '../DischargeSummaryEditor';
import { DISCHARGE_SUMMARY_STATUS } from './constants';
import { prepareDischargeSummaryEdit, summaryIsReadyForPrint } from './dischargeSummaryUtils';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import { useToast } from '../../../../hooks/use-toast';

const isMyAdmission = (adm, doctorUserId) => (
  doctorUserId && (
    adm.admitting_doctor_id === doctorUserId
    || adm.attending_physician_id === doctorUserId
    || adm.doctor_id === doctorUserId
  )
);

const DoctorDischargeSummaryPage = ({
  doctorsList = [],
  doctorUserId,
  filterToMyPatients = true,
}) => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/admissions', {
        params: { status: 'admitted', limit: 200 },
      });
      let active = res.data?.items || res.data || [];
      if (filterToMyPatients && doctorUserId) {
        active = active.filter((a) => isMyAdmission(a, doctorUserId));
      }

      const enriched = await Promise.all(active.map(async (a) => {
        try {
          const summaryRes = await axios.get(`/api/inpatient/admissions/${a.id}/discharge-summary`);
          return { ...a, summaryStatus: summaryRes.data?.status || 'draft' };
        } catch (err) {
          if (err.response?.status === 404) return { ...a, summaryStatus: 'missing' };
          return { ...a, summaryStatus: null };
        }
      }));

      enriched.sort((a, b) => {
        const rank = (s) => (s === 'missing' ? 0 : s === 'draft' ? 1 : 2);
        return rank(a.summaryStatus) - rank(b.summaryStatus);
      });
      setRows(enriched);
    } finally {
      setLoading(false);
    }
  }, [doctorUserId, filterToMyPatients]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const filtered = rows.filter((a) => {
    if (!q.trim()) return true;
    const needle = q.trim().toLowerCase();
    return (
      (a.patient_name || '').toLowerCase().includes(needle)
      || (a.admission_number || '').toLowerCase().includes(needle)
      || (a.room_number || '').toLowerCase().includes(needle)
    );
  });

  const openEditor = async (adm) => {
    setSelected(adm);
    try {
      await prepareDischargeSummaryEdit(adm.id);
      setEditorOpen(true);
      fetchRows();
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Could not open summary',
        description: typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail : 'Network error',
      });
    }
  };

  const printSummary = (adm) => {
    printPdfFromUrl(`/api/inpatient/admissions/${adm.id}/discharge-summary/pdf`);
  };

  return (
    <div className="space-y-4 max-w-4xl">
      <div>
        <h2 className="text-lg font-semibold">Discharge Summary</h2>
        <p className="text-sm text-gray-600 mt-1">
          Write the clinical discharge summary and mark it ready for print.
          Reception will settle the bill and issue the gate pass separately.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
        <Input
          className="pl-8"
          placeholder="Search patient, admission no., room…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {loading ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <Loader2 className="h-6 w-6 mx-auto animate-spin" />
            <p className="text-sm mt-2">Loading admissions…</p>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500 text-sm">
            {filterToMyPatients
              ? 'No active inpatients assigned to you.'
              : 'No admitted patients found.'}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {filtered.map((adm) => {
            const st = adm.summaryStatus;
            const statusMeta = st && DISCHARGE_SUMMARY_STATUS[st];
            const canPrint = summaryIsReadyForPrint(st);
            return (
              <Card key={adm.id} className="hover:bg-gray-50/80">
                <CardContent className="py-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-medium text-sm truncate">{adm.patient_name || 'N/A'}</div>
                    <div className="text-xs text-gray-500">
                      {adm.admission_number}
                      {adm.room_number ? ` · Room ${adm.room_number}` : ''}
                      {adm.doctor_name ? ` · Dr. ${adm.doctor_name}` : ''}
                    </div>
                    {statusMeta && (
                      <Badge className={`mt-1 text-xs ${statusMeta.className}`}>
                        {statusMeta.listLabel || statusMeta.label}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {canPrint && (
                      <Button size="sm" variant="outline" onClick={() => printSummary(adm)}>
                        <Printer className="h-3.5 w-3.5 mr-1" /> Print
                      </Button>
                    )}
                    <Button size="sm" onClick={() => openEditor(adm)}>
                      <FileText className="h-3.5 w-3.5 mr-1" />
                      {st === 'missing' ? 'Write summary'
                        : st === 'ready' ? 'Edit submitted summary'
                          : st === 'locked' ? 'View summary' : 'Continue'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <DischargeSummaryEditor
        open={editorOpen && !!selected}
        onClose={() => { setEditorOpen(false); setSelected(null); }}
        admissionId={selected?.id}
        admissionLabel={selected?.patient_name}
        doctorsList={doctorsList}
        onSaved={fetchRows}
      />
    </div>
  );
};

export default DoctorDischargeSummaryPage;
