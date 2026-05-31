# TODO: Add patient address (village, district) row to all PDF info boxes

User wants "village, district" on a single line inside the patient info box of every patient-facing PDF.

## Plan

1. Add a single helper to `PDFGenerator`: given a data dict, return a `"village, district"` string (skip empties, return empty string if neither present).
2. For every PDF builder that has a patient info table, append a full-width "Address" row at the bottom (SPAN'd across both columns). Only render when the address string is non-empty.
3. For every route that shapes the data dict, populate `village` and `district` from the patient row.

## PDF builders (file: `backend/app/utils/pdf_service.py`)

- [x] `generate_inpatient_bill_pdf` (info_data ~line 310)
- [x] `generate_bill_pdf` (patient_info_data ~line 771)
- [x] `generate_prescription_pdf` (info_data ~line 1114)
- [x] `generate_lab_report_pdf` (info_data ~line 1576)
- [x] `generate_combined_lab_report_pdf` (info_data ~line 1979)
- [x] `generate_discharge_summary_pdf` (patient_info_data ~line 2295)
- [x] `generate_deposit_receipt_pdf` (info_data ~line 2574)
- [x] `generate_refund_receipt_pdf` (meta_table ~line 2777)
- [x] `generate_credit_note_pdf` (meta ~line 2866)
- [x] `generate_consent_pdf` (meta_table ~line 3058)
- [x] `generate_death_certificate_pdf` (meta_table ~line 3165)
- [x] `generate_dama_pdf` (meta_table ~line 3256)
- [x] `generate_pharmacy_sale_invoice_pdf`
- [x] `generate_pharmacy_dispense_slip_pdf`

## Routes / data shapers (populate `village` + `district` on dict)

- [x] `appointments.py` (OPD bill data shaper for `generate_bill_pdf`)
- [x] `consultations.py` (consultation bill data)
- [x] `lab.py` (lab bill data — multiple call sites; lab report data — single + combined)
- [x] `hospital_admin.py` (custom bill helper)
- [x] `prescriptions_simple.py` (prescription_pdf_data)
- [x] `inpatient.py` — inpatient bill (already has it nested), discharge_data, deposit_data, refund, credit-note, consent, death certificate, DAMA
- [x] `pharmacy.py` (sale invoice + dispense slip)
