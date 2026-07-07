import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import DischargeSummaryPreviewCard from './DischargeSummaryPreviewCard';
import { summaryIsReadyForPrint } from './dischargeSummaryUtils';

const DischargeSummaryReview = ({
  summary,
  canWrite = false,
  onEdit,
  admissionId,
}) => {
  const handlePrint = () => {
    printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/discharge-summary/pdf`);
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Discharge summary (doctor → reception)</CardTitle>
      </CardHeader>
      <CardContent>
        <DischargeSummaryPreviewCard
          summary={summary}
          canWrite={canWrite}
          readOnly={summary?.status === 'locked'}
          onEdit={onEdit}
          onPrint={summaryIsReadyForPrint(summary?.status) ? handlePrint : undefined}
        />
      </CardContent>
    </Card>
  );
};

export default DischargeSummaryReview;
