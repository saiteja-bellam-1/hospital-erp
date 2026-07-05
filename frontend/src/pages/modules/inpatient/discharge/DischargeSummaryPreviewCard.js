import React from 'react';
import { Badge } from '../../../../components/ui/badge';
import { Button } from '../../../../components/ui/button';
import { CheckCircle2, Circle, FileText, Pencil, Printer, AlertTriangle } from 'lucide-react';

import { DISCHARGE_SUMMARY_STATUS } from './constants';

const STATUS = DISCHARGE_SUMMARY_STATUS;

const CHECKLIST = [
  { key: 'primary_diagnosis', label: 'Primary diagnosis' },
  { key: 'course_in_hospital', label: 'Hospital course' },
  { key: 'discharge_advice', label: 'Discharge advice' },
  { key: 'follow_up', label: 'Follow-up plan' },
  { key: 'take_home_medications', label: 'Take-home medicines', isArray: true },
];

function clip(text, max = 140) {
  if (!text) return '';
  const s = String(text).trim();
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

/**
 * Doctor / reception preview of discharge summary progress before opening the full editor.
 */
export default function DischargeSummaryPreviewCard({
  summary,
  canWrite = false,
  readOnly = false,
  onEdit,
  onPrint,
  compact = false,
}) {
  const st = summary?.status || 'missing';
  const badge = STATUS[st] || STATUS.missing;
  const canPrint = st === 'ready' || st === 'locked';
  const locked = st === 'locked' || readOnly;

  const checklist = CHECKLIST.map((item) => {
    const val = summary?.[item.key];
    const done = item.isArray
      ? Array.isArray(val) && val.some(m => (m.medicine_name || '').trim())
      : Boolean(String(val || '').trim());
    return { ...item, done };
  });
  const doneCount = checklist.filter(c => c.done).length;
  const canFinalize = doneCount >= 1 && Boolean(String(summary?.primary_diagnosis || '').trim());

  return (
    <div className="border rounded-lg bg-white overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b bg-slate-50">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
          <FileText className="h-4 w-4 text-blue-600" />
          Discharge Summary
          <Badge className={badge.className}>{badge.label}</Badge>
        </div>
        {!compact && st === 'draft' && (
          <span className="text-xs text-amber-700">
            {doneCount}/{checklist.length} sections filled
            {!canFinalize && ' · primary diagnosis required'}
          </span>
        )}
      </div>

      <div className="p-3 space-y-3 text-sm">
        {st === 'missing' && (
          <div className="flex items-start gap-2 text-amber-800 bg-amber-50 border border-amber-100 rounded p-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              {canWrite
                ? 'Write the discharge summary before reception can print it or complete checkout.'
                : 'Waiting for the treating doctor to write and mark the discharge summary ready for print.'}
            </span>
          </div>
        )}

        {st === 'draft' && !canWrite && (
          <div className="flex items-start gap-2 text-amber-800 bg-amber-50 border border-amber-100 rounded p-2 text-xs">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              Doctor has started the summary but not marked it <b>ready for print</b> yet.
              Reception can proceed once the doctor finalizes it.
            </span>
          </div>
        )}

        {(summary?.payer_label || summary?.department_name || summary?.surgery_date) && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
            {summary.department_name && (
              <span><span className="text-gray-400">Dept:</span> {summary.department_name}</span>
            )}
            {summary.payer_label && (
              <span><span className="text-gray-400">Payer:</span> {summary.payer_label}</span>
            )}
            {summary.surgery_date && (
              <span><span className="text-gray-400">Surgery:</span> {summary.surgery_date}</span>
            )}
          </div>
        )}

        {summary?.allergies_summary && (
          <div className="text-xs bg-amber-50 border border-amber-100 rounded px-2 py-1.5">
            <span className="font-medium text-amber-900">Allergies: </span>
            {summary.allergies_summary}
          </div>
        )}

        {!compact && st !== 'missing' && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1 text-xs">
            {checklist.map(item => (
              <li key={item.key} className="flex items-center gap-1.5">
                {item.done
                  ? <CheckCircle2 className="h-3.5 w-3.5 text-green-600 shrink-0" />
                  : <Circle className="h-3.5 w-3.5 text-gray-300 shrink-0" />}
                <span className={item.done ? 'text-gray-700' : 'text-gray-400'}>{item.label}</span>
              </li>
            ))}
          </ul>
        )}

        {summary && (summary.chief_complaint || summary.primary_diagnosis || summary.course_in_hospital) && (
          <div className="space-y-1.5 text-xs border-t pt-2">
            {summary.chief_complaint && (
              <div><span className="font-medium text-gray-600">Chief complaint: </span>{clip(summary.chief_complaint)}</div>
            )}
            {summary.primary_diagnosis && (
              <div><span className="font-medium text-gray-600">Diagnosis: </span>{clip(summary.primary_diagnosis)}</div>
            )}
            {summary.course_in_hospital && (
              <div><span className="font-medium text-gray-600">Course: </span>{clip(summary.course_in_hospital)}</div>
            )}
            {summary.follow_up && (
              <div><span className="font-medium text-gray-600">Follow-up: </span>{clip(summary.follow_up)}</div>
            )}
            {summary.finalized_by_name && (
              <div className="text-gray-400 pt-1">
                Finalized by {summary.finalized_by_name}
                {summary.finalized_at && ` · ${new Date(summary.finalized_at).toLocaleString()}`}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {canWrite && !locked && onEdit && (
            <Button size="sm" variant="outline" onClick={onEdit}>
              <Pencil className="h-3.5 w-3.5 mr-1" />
              {st === 'missing' ? 'Write summary' : 'Edit summary'}
            </Button>
          )}
          {canPrint && onPrint && (
            <Button size="sm" variant="outline" onClick={onPrint}>
              <Printer className="h-3.5 w-3.5 mr-1" /> Print
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
