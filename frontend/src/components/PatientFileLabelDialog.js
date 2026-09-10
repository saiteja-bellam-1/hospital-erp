import React from 'react';
import LabelPreviewDialog from './LabelPreviewDialog';
import { patientFileLabelParams, patientFileLabelPath } from '../utils/patientFileLabel';

/**
 * Preview/print dialog for patient file stickers.
 *
 * @param {boolean} open
 * @param {function} onClose
 * @param {number|string|null} patientId - int PK or UUID
 * @param {object} [context] - source / appointmentId / orderId / paymentMethod / etc.
 * @param {string} [title]
 */
export default function PatientFileLabelDialog({
  open,
  onClose,
  patientId,
  context = {},
  title = 'Patient File Label',
}) {
  if (!patientId) return null;
  return (
    <LabelPreviewDialog
      open={open}
      onClose={onClose}
      title={title}
      path={patientFileLabelPath(patientId)}
      params={patientFileLabelParams(context)}
      filename="patient_file_label.pdf"
      labelKind="patient_file"
    />
  );
}
