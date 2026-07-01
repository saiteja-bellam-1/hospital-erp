import React from 'react';
import { Button } from '../../../../components/ui/button';

const ACTIONS = [
  {
    key: 'finalBill',
    label: 'Final Bill',
    canKey: 'canPrintFinalBill',
    onKey: 'onPrintFinalBill',
    disabledTitle: 'Final bill not generated yet',
  },
  {
    key: 'dischargeSummary',
    label: 'Discharge Summary',
    canKey: 'canPrintDischargeSummary',
    onKey: 'onPrintDischargeSummary',
    disabledTitle: 'Discharge summary not ready',
  },
  {
    key: 'gatePass',
    label: 'Gate Pass',
    canKey: 'canPrintGatePass',
    onKey: 'onPrintGatePass',
    disabledTitle: 'Gate pass not issued yet',
  },
  {
    key: 'detailedSummary',
    label: 'Detailed Summary',
    canKey: 'canPrintDetailedSummary',
    onKey: 'onPrintDetailedSummary',
    disabledTitle: 'Detailed summary unavailable',
  },
];

/**
 * Standard discharge document print actions — final bill, discharge summary,
 * gate pass, and detailed admission summary.
 */
const DischargePrintBar = ({
  onPrintFinalBill,
  onPrintDischargeSummary,
  onPrintGatePass,
  onPrintDetailedSummary,
  canPrintFinalBill = false,
  canPrintDischargeSummary = false,
  canPrintGatePass = false,
  canPrintDetailedSummary = true,
  className = '',
  onClickStopPropagation = false,
}) => {
  const props = {
    onPrintFinalBill,
    onPrintDischargeSummary,
    onPrintGatePass,
    onPrintDetailedSummary,
    canPrintFinalBill,
    canPrintDischargeSummary,
    canPrintGatePass,
    canPrintDetailedSummary,
  };

  const stop = onClickStopPropagation
    ? (fn) => (e) => { e.stopPropagation(); fn?.(e); }
    : (fn) => fn;

  return (
    <div className={`flex flex-wrap items-center justify-end gap-1.5 ${className}`}>
      {ACTIONS.map(({ key, label, canKey, onKey, disabledTitle }) => {
        const enabled = props[canKey];
        const handler = props[onKey];
        return (
          <Button
            key={key}
            size="sm"
            variant="outline"
            className="h-8 text-xs whitespace-nowrap"
            title={enabled ? `Print ${label.toLowerCase()}` : disabledTitle}
            disabled={!enabled}
            onClick={stop(handler)}
          >
            {label}
          </Button>
        );
      })}
    </div>
  );
};

export default DischargePrintBar;
