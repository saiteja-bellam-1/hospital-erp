import React from 'react';
import { Textarea } from '../../../components/ui/textarea';

/**
 * Shared Complaints & History fields used by:
 * - Admit wizard Case Sheet step
 * - Discharge summary editor step 2
 *
 * `visible` / `labels` let the discharge editor gate by template blocks.
 */
export const CASE_SHEET_FIELD_KEYS = [
  'chief_complaint',
  'present_medical_history',
  'past_history',
  'family_history',
  'provisional_diagnosis',
  'physical_examination_notes',
  'findings_at_admission',
];

export const EMPTY_CASE_SHEET = {
  chief_complaint: '',
  present_medical_history: '',
  past_history: '',
  family_history: '',
  provisional_diagnosis: '',
  physical_examination_notes: '',
  findings_at_admission: '',
};

const DEFAULT_LABELS = {
  chief_complaint: 'Chief Complaints',
  present_medical_history: 'History of Present Illness',
  past_history: 'Past History / Previous Illness',
  family_history: 'Family History',
  provisional_diagnosis: 'Provisional Diagnosis',
  physical_examination_notes: 'Physical Examination (additional notes)',
  findings_at_admission: 'Key Findings at Admission',
};

const Section = ({ title, children }) => (
  <div className="space-y-2">
    <h4 className="text-sm font-semibold text-gray-800 border-b pb-1">{title}</h4>
    {children}
  </div>
);

const CaseSheetClinicalFields = ({
  values,
  onChange,
  disabled = false,
  /** When provided, only render fields whose key is truthy in this map. Default: all visible. */
  visible,
  /** Optional label overrides keyed by field name. */
  labels = {},
  /** Optional allergies line shown under chief complaints (discharge editor). */
  allergiesSummary,
  allergiesLabel = 'Allergies',
  /** Optional PE extras (include admission vitals checkbox). */
  showIncludeAdmissionVitals = false,
  includeAdmissionVitals,
  onIncludeAdmissionVitalsChange,
  chiefComplaintPlaceholder,
  physicalExamPlaceholder = 'Systemic examination notes',
  /** Rendered after provisional diagnosis (e.g. primary diagnosis in discharge editor). */
  afterProvisional = null,
}) => {
  const isVisible = (key) => (visible ? !!visible[key] : true);
  const label = (key) => labels[key] || DEFAULT_LABELS[key] || key;
  const setField = (key, value) => onChange?.({ [key]: value });

  return (
    <div className="space-y-4">
      {isVisible('chief_complaint') && (
        <Section title={label('chief_complaint')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.chief_complaint || ''}
            onChange={(e) => setField('chief_complaint', e.target.value)}
            placeholder={chiefComplaintPlaceholder}
          />
        </Section>
      )}

      {isVisible('present_medical_history') && (
        <Section title={label('present_medical_history')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.present_medical_history || ''}
            onChange={(e) => setField('present_medical_history', e.target.value)}
          />
        </Section>
      )}

      {allergiesSummary ? (
        <div className="text-sm bg-amber-50 border border-amber-100 rounded p-2">
          <span className="font-medium text-amber-900">{allergiesLabel} (from patient record): </span>
          {allergiesSummary}
        </div>
      ) : null}

      {isVisible('provisional_diagnosis') && (
        <Section title={label('provisional_diagnosis')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.provisional_diagnosis || ''}
            onChange={(e) => setField('provisional_diagnosis', e.target.value)}
          />
        </Section>
      )}

      {afterProvisional}

      {isVisible('past_history') && (
        <Section title={label('past_history')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.past_history || ''}
            onChange={(e) => setField('past_history', e.target.value)}
          />
        </Section>
      )}

      {isVisible('family_history') && (
        <Section title={label('family_history')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.family_history || ''}
            onChange={(e) => setField('family_history', e.target.value)}
          />
        </Section>
      )}

      {isVisible('physical_examination_notes') && (
        <Section title={label('physical_examination_notes')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.physical_examination_notes || ''}
            onChange={(e) => setField('physical_examination_notes', e.target.value)}
            placeholder={physicalExamPlaceholder}
          />
          {showIncludeAdmissionVitals && (
            <label className="flex items-center gap-2 text-xs text-gray-600 mt-1">
              <input
                type="checkbox"
                disabled={disabled}
                checked={includeAdmissionVitals !== false}
                onChange={(e) => onIncludeAdmissionVitalsChange?.(e.target.checked)}
              />
              Include first recorded admission vitals on printed summary
            </label>
          )}
        </Section>
      )}

      {isVisible('findings_at_admission') && (
        <Section title={label('findings_at_admission')}>
          <Textarea
            rows={2}
            disabled={disabled}
            value={values.findings_at_admission || ''}
            onChange={(e) => setField('findings_at_admission', e.target.value)}
          />
        </Section>
      )}
    </div>
  );
};

export default CaseSheetClinicalFields;
