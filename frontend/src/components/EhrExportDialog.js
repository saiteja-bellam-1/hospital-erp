import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { FileSpreadsheet, Download } from 'lucide-react';

export const EHR_EXPORT_SECTIONS = [
  { id: 'timeline', label: 'Timeline', description: 'Unified chronologic events' },
  { id: 'visits', label: 'Visits', description: 'Appointments and admissions' },
  { id: 'consultations', label: 'Consultations', description: 'Clinical encounters and diagnoses' },
  { id: 'prescriptions', label: 'Prescriptions', description: 'Medicines and instructions' },
  { id: 'lab', label: 'Lab', description: 'Orders and result values' },
  { id: 'pharmacy', label: 'Pharmacy', description: 'Pharmacy sales' },
  { id: 'billing', label: 'Billing', description: 'Bills and outstanding amounts' },
  { id: 'documents', label: 'Documents', description: 'Generated document index' },
];

/**
 * Popup to choose which patient-chart tabs to include in an Excel download.
 */
const EhrExportDialog = ({
  open,
  onClose,
  patientUuid,
  patientName,
  headers,
}) => {
  const [selected, setSelected] = useState(() =>
    Object.fromEntries(EHR_EXPORT_SECTIONS.map((s) => [s.id, true]))
  );
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) {
      setSelected(Object.fromEntries(EHR_EXPORT_SECTIONS.map((s) => [s.id, true])));
      setError('');
      setExporting(false);
    }
  }, [open]);

  const selectedIds = EHR_EXPORT_SECTIONS.map((s) => s.id).filter((id) => selected[id]);
  const allSelected = selectedIds.length === EHR_EXPORT_SECTIONS.length;

  const toggle = (id) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleAll = () => {
    const next = !allSelected;
    setSelected(Object.fromEntries(EHR_EXPORT_SECTIONS.map((s) => [s.id, next])));
  };

  const handleDownload = async () => {
    if (!patientUuid || selectedIds.length === 0) return;
    setExporting(true);
    setError('');
    try {
      const params = new URLSearchParams({ sections: selectedIds.join(',') });
      const res = await fetch(
        `/api/ehr/patient/${encodeURIComponent(patientUuid)}/export.xlsx?${params}`,
        { headers }
      );
      if (!res.ok) {
        let detail = 'Export failed';
        try {
          const body = await res.json();
          if (typeof body?.detail === 'string') detail = body.detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const disposition = res.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      const filename = match
        ? decodeURIComponent(match[1].replace(/"/g, '').trim())
        : `patient_chart_${patientUuid.slice(0, 8)}.xlsx`;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      window.URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      setError(err.message || 'Could not export Excel');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !exporting) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            Export to Excel
          </DialogTitle>
          <DialogDescription>
            Choose which chart tabs to include for{' '}
            <span className="font-medium text-foreground">{patientName || 'this patient'}</span>.
            Everything downloads as a single Excel sheet.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-700">Tabs to download</p>
            <button
              type="button"
              className="text-xs text-blue-600 hover:underline"
              onClick={toggleAll}
            >
              {allSelected ? 'Clear all' : 'Select all'}
            </button>
          </div>
          <div className="border rounded-lg divide-y max-h-[50vh] overflow-y-auto">
            {EHR_EXPORT_SECTIONS.map((section) => (
              <label
                key={section.id}
                className="flex items-start gap-3 p-3 hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-gray-300"
                  checked={Boolean(selected[section.id])}
                  onChange={() => toggle(section.id)}
                />
                <span>
                  <span className="block text-sm font-medium text-gray-900">{section.label}</span>
                  <span className="block text-xs text-gray-500">{section.description}</span>
                </span>
              </label>
            ))}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={exporting}>
            Cancel
          </Button>
          <Button
            onClick={handleDownload}
            disabled={exporting || selectedIds.length === 0 || !patientUuid}
          >
            <Download className="h-4 w-4 mr-1" />
            {exporting ? 'Downloading…' : 'Download Excel'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EhrExportDialog;
