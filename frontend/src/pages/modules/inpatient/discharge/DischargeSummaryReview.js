import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { FileText, Printer, AlertTriangle, Pencil } from 'lucide-react';
import { printPdfFromUrl } from '../../../../utils/printPdf';

const STATUS = {
  missing: { label: 'Not started', className: 'bg-gray-100 text-gray-700' },
  draft: { label: 'Doctor draft', className: 'bg-amber-100 text-amber-800' },
  ready: { label: 'Ready to print', className: 'bg-green-100 text-green-800' },
  locked: { label: 'Finalized', className: 'bg-slate-100 text-slate-700' },
};

const DischargeSummaryReview = ({
  summary,
  canWrite = false,
  onEdit,
  admissionId,
}) => {
  const st = summary?.status || 'missing';
  const badge = STATUS[st] || STATUS.missing;
  const canPrint = st === 'ready' || st === 'locked';

  const handlePrint = () => {
    printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/discharge-summary/pdf`);
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Discharge Summary
          <Badge className={badge.className}>{badge.label}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {st === 'missing' && (
          <div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              Waiting for the treating doctor to write and finalize the discharge summary.
              {canWrite && ' You can open the editor below.'}
            </div>
          </div>
        )}

        {st === 'draft' && (
          <div className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            Summary is still a draft. The doctor must mark it <b>ready for print</b> before reception can print it or discharge can proceed.
          </div>
        )}

        {summary?.primary_diagnosis && (
          <div className="text-sm space-y-1 border rounded p-3 bg-gray-50">
            <div><span className="font-medium">Primary diagnosis:</span> {summary.primary_diagnosis}</div>
            {summary.course_in_hospital && (
              <div><span className="font-medium">Course:</span> {summary.course_in_hospital.slice(0, 200)}
                {summary.course_in_hospital.length > 200 ? '…' : ''}
              </div>
            )}
            {summary.finalized_by_name && (
              <div className="text-xs text-gray-500">
                Finalized by {summary.finalized_by_name}
                {summary.finalized_at && ` · ${new Date(summary.finalized_at).toLocaleString()}`}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {canWrite && st !== 'locked' && (
            <Button variant="outline" onClick={onEdit}>
              <Pencil className="h-4 w-4 mr-1" />
              {st === 'missing' ? 'Write summary' : 'Edit summary'}
            </Button>
          )}
          {canPrint && (
            <Button onClick={handlePrint}>
              <Printer className="h-4 w-4 mr-1" /> Print discharge summary
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default DischargeSummaryReview;
